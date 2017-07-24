from django.shortcuts import redirect, render, get_object_or_404
from django.http import JsonResponse
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import ensure_csrf_cookie
from simple_history.utils import update_change_reason

from .models import Tag, Article
from .forms import ArticleForm
from ..auth.decorators import superuser_required


def read_article_view(request, article_slug, revision_id=None):
    """Read an article"""

    if revision_id is not None and request.user.is_superuser:
        article = get_object_or_404(Article, slug=article_slug)
        public_article = article.get_revision(revision_id)
        if 'text' in request.GET:
            return JsonResponse({
                'title': public_article.title,
                'html': public_article.html,
                'tags': [tag.name for tag in public_article.tags.all()]
            })
    else:
        article = get_object_or_404(Article, slug=article_slug, publish_id__isnull=False)
        public_article = article.published_article
    return render(request, 'docs/read.html', {
        'article': public_article,
        'revision': revision_id
    })


def list_articles_view(request):
    """Index of articles."""

    tags = []
    if 'all' in request.GET and request.user.is_superuser:
        available_articles = Article.objects.all()
    else:
        available_articles = Article.objects.filter(publish_id__isnull=False)
    if 'tags' in request.GET:
        tags = request.GET['tags'].split(' ')
    if len(tags) > 0:
        public_articles = available_articles.filter(tags__name__in=tags).distinct()
    else:
        public_articles = available_articles

    return render(request, 'docs/list.html', {
        'articles': public_articles
    })


def index_view(request):
    """Home page for documentation"""

    tags = Tag.objects.filter(article__publish_id__isnull=False).distinct()
    return render(request, 'docs/home.html', {'tags': tags})


@superuser_required
def article_history_view(request, article_slug):
    article = Article.objects.get(slug=article_slug)
    revisions = article.history.all()
    messages.info(request, '{} revisions fetched'.format(len(revisions)))
    return render(request, 'docs/history.html', {
        'article_slug': article.slug,
        'revisions': revisions,
        'publish_id': article.publish_id
    })


@superuser_required
def new_article_view(request):
    """Write a new document"""
    if request.method == 'POST':
        form = ArticleForm(request.POST)
        if form.is_valid():
            tags = form.cleaned_data['tags']
            article = form.save(commit=True)
            article.save()
            for tag_name in tags.split(','):
                tag, created = Tag.objects.get_or_create(name=tag_name.lower())
                article.tags.add(tag)
            article.save(history=True)
            update_change_reason(article, "Initial Save")
            messages.success(request, 'Successfuly created document')
            return redirect('edit_article', article_slug=article.slug)
        messages.error(request, 'Invalid form')
        return render(request, 'docs/edit.html', {'form': form})

    tags = Tag.objects.all()
    form = ArticleForm()
    return render(request, 'docs/edit.html', {'form': form, 'tags': tags})


@superuser_required
def edit_article_view(request, article_slug):
    """Edit preexisting article"""
    article = get_object_or_404(Article, slug=article_slug)
    tags = Tag.objects.all()

    form = ArticleForm(instance=article)
    return render(request, 'docs/edit.html', {
        'form': form,
        'tags': tags,
        'slug': article.slug,
        'article_tags': article.tags.all()
    })


@require_http_methods(['POST'])
@superuser_required
def save_view(request, article_slug):
    article = get_object_or_404(Article, slug=article_slug)
    form = ArticleForm(request.POST, instance=article)
    if form.is_valid():
        tags = form.cleaned_data['tags']
        article = form.save(commit=True)
        article.tags.clear()
        for tag_name in tags.split(','):
            tag, created = Tag.objects.get_or_create(name=tag_name.lower())
            article.tags.add(tag)
            article.save()
        return JsonResponse({'success': 'Successfully saved document.'})
    return JsonResponse({'error': 'Invalid Form'})


@require_http_methods(['POST'])
@superuser_required
def save_history_view(request, article_slug):
    article = get_object_or_404(Article, slug=article_slug)
    form = ArticleForm(request.POST, instance=article)
    if form.is_valid():
        tags = form.cleaned_data['tags']
        article = form.save(commit=True)
        article.tags.clear()
        for tag_name in tags.split(','):
            tag, created = Tag.objects.get_or_create(name=tag_name.lower())
            if tag not in article.tags.all():
                article.tags.add(tag)
        article.save(history=True)
        if 'reason' in form.cleaned_data:
            update_change_reason(article, form.cleaned_data['reason'])
        return JsonResponse({
            'success': 'Successfully created revision with ID#{}'.format(article.history.first().history_id),
            'rid': article.history.first().history_id
        })
    return JsonResponse({'error': 'Invalid Form'})


@require_http_methods(['POST'])
@superuser_required
@ensure_csrf_cookie
def publish_view(request, article_slug):
    """Publish specified revision"""
    article = get_object_or_404(Article, slug=article_slug)
    revision_id = request.POST['revision_id']
    try:
        article.publish_id = revision_id
        article.save()
        return JsonResponse({'success': True})
    except:
        return JsonResponse({'success': False})


@require_http_methods(['POST'])
@superuser_required
@ensure_csrf_cookie
def unpublish_view(request, article_slug):
    """Mark article as unpublished"""
    article = get_object_or_404(Article, slug=article_slug)
    try:
        article.publish_id = None
        article.save()
        return JsonResponse({'success': True})
    except:
        return JsonResponse({'success': False})