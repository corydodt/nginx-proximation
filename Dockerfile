# vim:set ft=dockerfile:
FROM corydodt/circus-base

RUN mkdir -p /usr/share/nginx/html /run/nginx /opt/Proximation /etc/letsencrypt/live
ENV PYTHONPATH=/opt/Proximation
WORKDIR /opt/Proximation

COPY ./requirements.txt /opt/Proximation/

COPY ./0*.ini /etc/circus.d/

RUN apk update \
    && apk add --no-cache --virtual build-dependencies \
        libffi-dev \
        openssl-dev \
        python-dev \
    && apk add --no-cache \
        bash \
        ca-certificates \
        # g++ required for circusd's use of cython
        g++ \
        net-tools \
        nginx \
        openssl \
    && pip install -U --no-cache-dir -r /opt/Proximation/requirements.txt \
    && apk del build-dependencies

COPY ./http.conf.in \
     ./proximation.py \
    /opt/Proximation/

EXPOSE 80 443
