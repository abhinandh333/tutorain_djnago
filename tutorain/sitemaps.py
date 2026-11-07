from django.contrib.sitemaps import Sitemap
from django.urls import reverse


class StaticViewSitemap(Sitemap):
    priority = 0.8
    changefreq = 'weekly'

    def items(self):
        return ['home','tutor_panel','findsub', 'contact','maca','download','free_classes','abhinandh','ceo']

    def location(self, item):
        return reverse(item)