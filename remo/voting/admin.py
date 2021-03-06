from django.contrib import admin

from import_export.admin import ExportMixin

from remo.voting.models import (Poll, PollComment, RadioPoll, RadioPollChoice, RangePoll,
                                RangePollChoice, Vote)


class VoteInline(admin.StackedInline):
    """Vote model inline."""
    model = Vote
    extra = 0


class RangePollChoiceInline(admin.StackedInline):
    """Poll Range Votes Inline."""
    model = RangePollChoice
    extra = 0
    readonly_fields = ['votes']


class RangePollInline(admin.StackedInline):
    """Range Poll Inline."""
    model = RangePoll
    extra = 0


class RadioPollChoiceInline(admin.StackedInline):
    """Radio Poll Choice Inline."""
    model = RadioPollChoice
    extra = 0
    readonly_fields = ['votes']


class RadioPollInline(admin.StackedInline):
    """Poll Radio Inline."""
    model = RadioPoll
    extra = 0


class RadioPollAdmin(ExportMixin, admin.ModelAdmin):
    inlines = [RadioPollChoiceInline]


class RangePollAdmin(ExportMixin, admin.ModelAdmin):
    inlines = [RangePollChoiceInline]


class PollCommentInline(admin.StackedInline):
    """PollComment Inline."""
    model = PollComment


class PollAdmin(ExportMixin, admin.ModelAdmin):
    """Voting Admin."""

    inlines = [RangePollInline, RadioPollInline, PollCommentInline, VoteInline]
    search_fields = ['name']
    list_display = ['name', 'start', 'end', 'valid_groups']
    date_hierarchy = 'start'
    readonly_fields = ['task_start_id', 'task_end_id']
    list_filter = ['automated_poll', 'is_extended', 'comments_allowed']
    actions = ['delete_model']

    def delete_model(self, request, obj):
        """Handle celery revocation before deleting the object."""
        # Avoid circular dependencies
        from remo.base.tasks import app as celery_app

        if obj.task_end_id:
            celery_app.control.revoke(obj.task_end_id)
        if obj.task_start_id:
            celery_app.control.revoke(obj.task_start_id)
        obj.delete()


class VoteAdmin(ExportMixin, admin.ModelAdmin):
    """Vote Admin"""
    model = Vote
    search_fields = ['user__first_name', 'user__last_name', 'poll__name']
    list_display = ['user', 'poll', 'date_voted']


admin.site.register(Vote, VoteAdmin)
admin.site.register(RangePoll, RangePollAdmin)
admin.site.register(RadioPoll, RadioPollAdmin)
admin.site.register(Poll, PollAdmin)
