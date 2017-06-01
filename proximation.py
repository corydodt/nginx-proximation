#!/usr/bin/env python
"""
The proximation service
"""
import os
import signal

import yaml

from twisted.internet import reactor

import attr

from jinja2 import Template

from codado.dockerish import DockerEngine


TEMPLATE = 'http.conf.in'
TEMPLATE_OUT = '/etc/nginx/conf.d/default.conf'
NGINX_PIDFILE = '/run/nginx/nginx.pid'


@attr.s
class EventWatcher(object):
    """
    Look for any started docker containers and build the nginx config based
    on their environment
    """
    engine = DockerEngine()
    _virtualHosts = attr.ib(default=attr.Factory(dict))

    def _scanContainers(self):
        """
        Rebuild internal container dict by looking at existing containers

        Returns a set of differences if the containers have changed
        """
        kv = lambda s: s.split('=', 1)
        running = self.engine.client.containers.list(filters={'status':'running'})
        vhosts = {}
        for c in running:
            env = {k: v for (k, v) in (kv(s) for s in c.attrs['Config']['Env'])}
            if 'virtual_host' in env:
                vhosts.setdefault(env['virtual_host'], []).append(c)
        if vhosts != self._virtualHosts:
            self._virtualHosts = vhosts
            u8 = lambda x: x.encode('utf-8')
            hn = lambda con: u8(con.attrs['Config']['Hostname'])
            fmtd = {u8(x): map(hn, y) for (x, y) in vhosts.items()}
            return yaml.dump(fmtd, default_flow_style=False)

        return False

    @engine.handler("dockerish.init")
    @engine.handler("container.stop")
    @engine.handler("container.pause")
    @engine.handler("container.start")
    @engine.handler("container.die")
    @engine.handler("container.kill")
    @engine.handler("container.unpause")
    def onStart(self, event):
        """
        Rebuild the nginx config
        """
        print event.name
        modified = self._scanContainers()
        if modified:
            self.render(TEMPLATE, event)
            # TODO: defer this a few seconds
            self.reload()
            print 'Hosts:'
            print modified

    @property
    def pemsAvailable(self):
        return [d for d in os.listdir('/etc/letsencrypt/live') if
                os.path.isdir(d)]

    def reload(self):
        """
        Signal nginx to reload config
        """
        # TODO: test with nginx -T
        pid = int(open(NGINX_PIDFILE).read())
        os.kill(pid, signal.SIGHUP)

    def render(self, tplFile, event):
        """
        Render the template 
        """
        inputFile = open(tplFile, 'rb')
        tpl = Template(inputFile.read())
        env = dict(__environ__=os.environ,
                event=event,
                virtual_hosts=self._virtualHosts,
                https_conf={k: 1 for k in self.pemsAvailable},
                **os.environ)
        open(TEMPLATE_OUT, 'wb').write(
            tpl.render(**env)
            )
        print 'Rendered %r' % TEMPLATE_OUT


def main():
    ew = EventWatcher()
    # TODO: shut down early if the docker socket can't be found
    reactor.callWhenRunning(ew.engine.run)
    reactor.run()


main()
