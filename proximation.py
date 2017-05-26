"""
The proximation service
"""
from twisted.internet import reactor

from codado.dockerish import DockerEngine


class EventWatcher(object):
    """
    Look for any started docker containers and build the nginx config based
    on their environment
    """
    engine = DockerEngine()

    @engine.handler("container.start")
    def onStart(self, event):
        """
        Display the environment of a started container
        """
        c = event.container
        print '+' * 5, 'started:', c
        kv = lambda s: s.split('=', 1)
        env = {k: v for (k, v) in (kv(s) for s in c.attrs['Config']['Env'])}
        print env


def main():
    ew = EventWatcher()
    # TODO: shut down early if the docker socket can't be found
    reactor.callWhenRunning(ew.engine.run)
    reactor.run()


main()
