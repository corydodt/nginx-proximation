# nginx-proximation
Automate the proxying and encryption of HTTP applications - service &amp; container image

## Use case

If you have:
- a web application or service that you want to serve using HTTPS,
- and you want to place it behind a reverse proxy,
- and you want a certificate set up for you transparently (and freely),

then nginx-proximation is a good place to start.

This is good in environments like Amazon ECS, if you want to transparently
upgrade services with zero downtime. The author created this to avoid resource
conflicts with exposed ports; using this technique, you can place a
heavyweight application behind a very lightweight nginx-proximation service
which stays running forever. When you upgrade the heavyweight application by
starting a new container for it, nginx-proximation will automatically adjust
to the IP and port of the new upstream container.

### Install/build

You may fetch the latest build with `docker pull nginx-proximation:latest`, or
build:

```
docker build . -t corydodt/nginx-proximation:latest
```

### Use:

1. Create the file envfile, with the following contents:
```
certbot_email=...your@email.address..
# while testing, --staging keeps letsencrypt from blocking you
certbot_flags=--staging
```

Once you have successfully tested, you should take out `certbot_flags` to get
a production certificate from LetsEncrypt.

2. Create a directory for storing your certs between tests. You will want to
   always pass in a cert volume to nginx-proximation so you do not scrap your
   certs accidentally.

`mkdir letsencrypt`

3. Launch nginx-proximation. You need access to docker.sock within the
   container so proximation can react to start/stop events of other
   containers.

```
docker run -d \
    -v /var/run/docker.sock:/var/run/docker.sock \
    -v letsencrypt:/etc/letsencrypt \
    --env-file=envfile \
    corydodt/nginx-proximation:latest
```

4. Launch other containers, using the `public_hostname` environment variable.
   You will additionally need to expose a port in your other containers.
   Use `private_port` to specify the port you want to be proxied.

```
docker run -d \
  -p :9999 \
  -e public_hostname=yourhost.yourdomain.com \
  -e private_port=9999 \
  your/container:latest
```

The command above will launch your/container:latest, exposing port 9999 (the
port number inside the container), using an ARBITRARY port in the host. The
environment variables specify that:
- yourhost.yourdomain.com will be the certificate requested from certbot, and
- port 9999/tcp will be mapped to nginx by proximation.

Proximation finds the correct HostPort by inspecting attributes of the
container and finding the exposed port that matches 9999/tcp. (This is usually
something like 36799.)

5. (Wait a few seconds for certbot to run, then ...) visit
   https://yourhost.yourdomain.com/

### Monitoring

Running `docker logs -f` on the nginx-proximation container, you will see it
report each time a container is stopped or started, and the virtual hosts it
currently is keeping track of.

When you start a new `virtual_host` container, you will see output like the
following:
```
2017-06-08 06:22:40 [10] | Attempting to get cert for u'c00151ed.ngrok.io'
2017-06-08 06:22:40 [10] | Now:
2017-06-08 06:22:40 [10] |   c00151ed.ngrok.io: e8242d544ecd:36799
```

Each time this happens, nginx-proximation has:
- regenerated the nginx config, and
- sent SIGHUP to nginx to reload its config.

If you add more containers with different values for `virtual_host`,
nginx-proximation will track those as well. If you have multiple containers
for the same virtual host, you may see multiple container ids next to each
vhost in the list.

Each time you add a `virtual_host` which *does not* have a certificate in
`/etc/letsencrypt/live`, nginx-proximation will run certbot to acquire a cert
for it. When it successfully acquires a cert (usually within a few seconds),
you will see output like the following:

```
2017-06-08 06:22:45 [10] | Now:
2017-06-08 06:22:45 [10] |   c00151ed.ngrok.io[TLS]: e8242d544ecd:36799
```

Errors from certbot will also be displayed in the log output.

### Management

- You should back up the letsencrypt volume when your certificates change.

- Containers which are already running when nginx-proximation starts will
  automatically be added to its list of virtual hosts.

- When a virtual host appears, if it already has files in /etc/letsencrypt/live
  then nginx-proximation will automatically use those certificates. Thus, when
  you mount /etc/letsencrypt as a volume from outside, you can tear down
  nginx-proximation itself, and restart it, without losing any state.

