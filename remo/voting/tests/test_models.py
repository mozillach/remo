import datetime

from django.conf import settings
from django.contrib.auth.models import Group, User
from django.core import mail
from django.utils.timezone import now

from mock import patch
from nose.tools import eq_, ok_
from test_utils import TestCase

from remo.profiles.tests import UserFactory
from remo.remozilla.tests import BugFactory
from remo.voting.models import (BUGZILLA_URL, Poll,
                                automated_poll_discussion_email)
from remo.voting.tests import (PollCommentFactory, PollCommentFactoryNoSignals,
                               PollFactory, PollFactoryNoSignals)


class VotingMailNotificationTest(TestCase):
    """Tests related to Voting Models."""
    fixtures = ['demo_users.json']

    def setUp(self):
        """Initial data for the tests."""
        self.user = User.objects.get(username='admin')
        self.group = Group.objects.get(name='Admin')
        self._now = now()
        self.now = self._now.replace(microsecond=0)
        self.start = self.now
        self.end = self.now + datetime.timedelta(days=5)
        self.voting = Poll(name='poll', start=self.start, end=self.end,
                           valid_groups=self.group, created_by=self.user)
        self.voting.save()

    def test_send_email_on_save_poll(self):
        """Test sending emails when a new voting is added."""
        recipients = map(lambda x: '%s' % x.email,
                         User.objects.filter(groups=self.group))
        eq_(len(mail.outbox), 2)
        ok_(mail.outbox[0].to[0] in recipients)
        ok_(mail.outbox[1].to[0] in recipients)

    @patch('remo.voting.models.celery_control.revoke')
    def test_send_email_on_edit_poll(self, fake_revoke):
        """Test sending emails when the poll is edited."""
        Poll.objects.filter(pk=self.voting.id).update(task_start_id='1234',
                                                      task_end_id='1234')
        poll = Poll.objects.get(pk=self.voting.id)
        poll.name = 'Edit Voting'
        if not settings.CELERY_ALWAYS_EAGER:
            fake_revoke.return_value = True
        poll.save()
        eq_(len(mail.outbox), 3)


class AutomatedRadioPollTest(TestCase):
    """Tests the automatic creation of new Radio polls."""
    fixtures = ['demo_users.json']

    def test_automated_radio_poll_valid_bug(self):
        """Test the creation of an automated radio poll."""
        UserFactory.create(username='remobot')
        bug = BugFactory.create(council_vote_requested=True,
                                component='Budget Requests')
        poll = Poll.objects.get(bug=bug)
        eq_(poll.bug.bug_id, bug.bug_id)
        eq_(poll.description, bug.first_comment)
        eq_(poll.name, bug.summary)

    def test_automated_radio_poll_no_auto_bug(self):
        """Test the creation of an automated radio
        poll with a non budget/swag bug.

        """
        BugFactory.create()
        eq_(Poll.objects.filter(automated_poll=True).count(), 0)

    def test_automated_radio_poll_already_exists(self):
        """Test that a radio poll is not created
        if the bug already exists.

        """
        UserFactory.create(username='remobot')
        bug = BugFactory.create(council_vote_requested=True,
                                component='Budget Requests')
        bug.first_comment = 'My first comment.'
        bug.save()
        eq_(Poll.objects.filter(automated_poll=True).count(), 1)

    def test_send_discussion_email_to_council(self):
        bug = BugFactory.create(bug_id=989812)
        automated_poll = PollFactory.build(
            name='automated_poll', automated_poll=True, bug=bug)

        with patch('remo.voting.models.send_remo_mail') as mocked_send_mail:
            automated_poll_discussion_email(None, automated_poll, True, {})

        subject = 'Discuss [Bug 989812] - Bug summary'
        data = {'bug': bug, 'BUGZILLA_URL': BUGZILLA_URL,
                'poll': automated_poll}
        mocked_send_mail.delay.assert_called_once_with(
            subject=subject,
            email_template='emails/review_budget_notify_council.txt',
            recipients_list=[settings.REPS_COUNCIL_ALIAS],
            data=data)

    def test_send_discussion_email_to_council_edit(self):
        bug = BugFactory.create(bug_id=989812)
        automated_poll = PollFactory.build(
            name='automated_poll', automated_poll=True, bug=bug)

        with patch('remo.voting.models.send_remo_mail') as mocked_send_mail:
            automated_poll_discussion_email(None, automated_poll, False, {})

        ok_(not mocked_send_mail.called)


class VotingCommentSignalTests(TestCase):
    def test_comment_one_user(self):
        """Test sending email when a new comment is added on a Poll
        and the user has the option enabled in his/her settings.
        """
        commenter = UserFactory.create()
        creator = UserFactory.create(
            userprofile__receive_email_on_add_voting_comment=True)
        # Disable notifications related to the creation of a poll
        poll = PollFactoryNoSignals.create(created_by=creator)
        PollCommentFactory.create(user=commenter, poll=poll,
                                  comment='This is a comment')

        eq_(len(mail.outbox), 1)
        eq_('%s <%s>' % (creator.get_full_name(), creator.email),
            mail.outbox[0].to[0])
        msg = ('[Voting] User {0} commented on {1}'
               .format(commenter.get_full_name(), poll))
        eq_(mail.outbox[0].subject, msg)

    def test_one_user_settings_False(self):
        """Test sending email when a new comment is added on a Poll
        and the user has the option disabled in his/her settings.
        """
        comment_user = UserFactory.create()
        user = UserFactory.create(
            userprofile__receive_email_on_add_voting_comment=False)
        poll = PollFactoryNoSignals.create(created_by=user)
        PollCommentFactory.create(user=comment_user, poll=poll,
                                  comment='This is a comment')

        eq_(len(mail.outbox), 0)

    def test_comment_multiple_users(self):
        """Test sending email when a new comment is added on a Poll
        and the users have the option enabled in their settings.
        """
        commenter = UserFactory.create()
        creator = UserFactory.create(
            userprofile__receive_email_on_add_voting_comment=True)
        poll = PollFactoryNoSignals.create(created_by=creator)
        users_with_comments = UserFactory.create_batch(
            2, userprofile__receive_email_on_add_voting_comment=True)
        # disconnect the signals in order to add two users in PollComment
        for user_obj in users_with_comments:
            PollCommentFactoryNoSignals.create(
                user=user_obj, poll=poll, comment='This is a comment')
        PollCommentFactory.create(user=commenter, poll=poll,
                                  comment='This is a comment')

        eq_(len(mail.outbox), 3)
        recipients = ['%s <%s>' % (creator.get_full_name(), creator.email),
                      '%s <%s>' % (users_with_comments[0].get_full_name(),
                                   users_with_comments[0].email),
                      '%s <%s>' % (users_with_comments[1].get_full_name(),
                                   users_with_comments[1].email)]
        receivers = [mail.outbox[0].to[0], mail.outbox[1].to[0],
                     mail.outbox[2].to[0]]
        eq_(set(recipients), set(receivers))
        msg = ('[Voting] User {0} commented on {1}'
               .format(commenter.get_full_name(), poll))
        eq_(mail.outbox[0].subject, msg)
