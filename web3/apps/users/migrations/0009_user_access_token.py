# -*- coding: utf-8 -*-
# Generated by Django 1.10.3 on 2016-12-14 02:00
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0008_user_github_token'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='access_token',
            field=models.CharField(blank=True, max_length=64),
        ),
    ]