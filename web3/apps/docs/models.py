import re

from django.db import models
from django.template.defaultfilters import slugify
from simple_history.models import HistoricalRecords

import markdown2

from ..helpers import ModelDiffMixin
from ..users.models import User


class Tag(models.Model):

    """Tag for article"""

    name = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.name


class Article(models.Model, ModelDiffMixin):

    """A piece of documentation"""

    title = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True)
    tags = models.ManyToManyField(Tag)
    author = models.ManyToManyField(User)

    content = models.TextField()

    history = HistoricalRecords()
    publish_id = models.IntegerField(null=True, blank=True)

    @property
    def publish_date(self):
        return self.history.get(history_id=self.publish_id).history_date

    @property
    def is_public(self):
        return self.publish_id is not None

    @property
    def published_article(self):
        """returns article that matches publish_id """
        return self.history.get(history_id=self.publish_id).instance

    def get_revision(self, revision_id):
        return self.history.get(history_id=revision_id).instance

    @property
    def html(self):
        link_patterns = [(re.compile(r'((([A-Za-z]{2,9}:(?:\/\/)?)(?:[\-;:&=\+\$,\w]+@)?[A-Za-z0-9\.\-]+(:[0-9]+)?|(?:www\.|[\-;:&=\+\$,\w]+@)[A-Za-z0-9\.\-]+)((?:\/[\+~%\/\.\w\-_]*)?\??(?:[\-\+=&;%@\.\w_]*)#?(?:[\.\!\/\\\w]*))?)'), r'\1')]
        return markdown2.markdown(self.content, extras=[
            'fenced-code-blocks',
            'header-ids',
            'tables',
            'code-friendly'
        ], link_patterns=link_patterns)

    def save(self, history=False, *args, **kwargs):
        if not self.id:
            self.slug = slugify(self.title)
        if not self.id or history:
            super().save(*args, **kwargs)
        else:
            self.skip_history_when_saving = True
            try:
                super().save(*args, **kwargs)
            finally:
                del self.skip_history_when_saving