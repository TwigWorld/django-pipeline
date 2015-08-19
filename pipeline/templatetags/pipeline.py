from __future__ import unicode_literals

from django.contrib.staticfiles.storage import staticfiles_storage

from django import template
from django.template.loader import render_to_string
from django.utils.safestring import mark_safe

from ..collector import default_collector
from ..conf import settings
from ..packager import Packager, PackageNotFound
from ..utils import guess_type


register = template.Library()


class PipelineMixin(object):

    def get_package_or_none(self, package_name, package_type):
        package = {
            'js': getattr(settings, 'PIPELINE_JS', {}).get(package_name, {}),
            'css': getattr(settings, 'PIPELINE_CSS', {}).get(package_name, {}),
        }[package_type]

        if package:
            return {package_name: package}

    def _compressed_override_name(self, name):
       return '{prefix}_{name}'.format(
           prefix=getattr(settings, 'PIPELINE_SETTINGS_PREFIX',''),
           name=name
       )

    def package_for(self, package_name, package_type):
        override_package = self._compressed_override_name(package_name)
        package = self.get_package_or_none(override_package, package_type)

        if not package:
            package = self.get_package_or_none(package_name, package_type)
            override_package = package_name

        packager = {
            'js': Packager(css_packages={}, js_packages=package),
            'css': Packager(css_packages=package, js_packages={}),
        }[package_type]

        return packager.package_for(package_type, override_package)

    def render_compressed(self, package, package_type):
        if settings.PIPELINE_ENABLED:
            method = getattr(self, "render_{0}".format(package_type))
            return method(package, package.output_filename)
        else:
            default_collector.collect()

            packager = Packager()
            method = getattr(self, "render_individual_{0}".format(package_type))
            paths = packager.compile(package.paths)
            templates = packager.pack_templates(package)
            return method(package, paths, templates=templates)

    def gzip_allowed(self, http_accepts):
        return 'gzip' in http_accepts and\
            settings.PIPELINE_ENABLED and getattr(settings, 'AWS_IS_GZIPPED', False)


class StylesheetNode(PipelineMixin, template.Node):
    def __init__(self, name):
        self.name = name
        self.gzip=False

    def render(self, context):
        package_name = template.Variable(self.name).resolve(context)
        try:
            package = self.package_for(package_name, 'css')
            self.gzip = self.gzip_allowed(context['request'].META.get('HTTP_ACCEPT_ENCODING', ''))
        except PackageNotFound:
            return ''  # fail silently, do not return anything if an invalid group is specified
        return self.render_compressed(package, 'css')

    def render_css(self, package, path):
        template_name = package.template_name or "pipeline/css.html"
        context = package.extra_context
        url = mark_safe(staticfiles_storage.url(path))

        if self.gzip == True:
            url += '.gz'

        context.update({
            'type': guess_type(path, 'text/css'),
            'url': url
        })

        return render_to_string(template_name, context)

    def render_individual_css(self, package, paths, **kwargs):
        tags = [self.render_css(package, path) for path in paths]
        return '\n'.join(tags)


class JavascriptNode(PipelineMixin, template.Node):
    def __init__(self, name):
        self.name = name
        self.gzip=False

    def render(self, context):
        package_name = template.Variable(self.name).resolve(context)
        try:
            package = self.package_for(package_name, 'js')
            self.gzip = self.gzip_allowed(context['request'].META.get('HTTP_ACCEPT_ENCODING', ''))
        except PackageNotFound:
            return ''  # fail silently, do not return anything if an invalid group is specified
        return self.render_compressed(package, 'js')

    def render_js(self, package, path):
        template_name = package.template_name or "pipeline/js.html"
        context = package.extra_context
        url = mark_safe(staticfiles_storage.url(path))

        if self.gzip == True:
            url += '.gz'
        context.update({
            'type': guess_type(path, 'text/css'),
            'url': url
        })
        return render_to_string(template_name, context)

    def render_inline(self, package, js):
        context = package.extra_context
        context.update({
            'source': js
        })
        return render_to_string("pipeline/inline_js.html", context)

    def render_individual_js(self, package, paths, templates=None):
        tags = [self.render_js(package, js) for js in paths]
        if templates:
            tags.append(self.render_inline(package, templates))
        return '\n'.join(tags)


@register.tag
def stylesheet(parser, token):
    try:
        tag_name, name = token.split_contents()
    except ValueError:
        raise template.TemplateSyntaxError('%r requires exactly one argument: the name of a group in the PIPELINE_CSS setting' % token.split_contents()[0])
    return StylesheetNode(name)


@register.tag
def javascript(parser, token):
    try:
        tag_name, name = token.split_contents()
    except ValueError:
        raise template.TemplateSyntaxError('%r requires exactly one argument: the name of a group in the PIPELINE_JS setting' % token.split_contents()[0])
    return JavascriptNode(name)
