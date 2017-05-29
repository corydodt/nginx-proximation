# vim:set ft=dockerfile:
FROM alpine:3.5

RUN mkdir -p /usr/share/nginx/html /run/nginx /opt/Proximation
ENV PYTHONPATH=/opt/Proximation PYTHONUNBUFFERED=true
WORKDIR /opt/Proximation

COPY ./get-pip.py \
     ./requirements.txt \
     ./http.conf.in \
     ./circus.ini \
     ./proximation.py \
    /opt/Proximation/

COPY ./codado /opt/Proximation/codado

RUN apk update \
    && apk add --no-cache --virtual build-dependencies \
        libffi-dev \
        openssl-dev \
        python-dev \
        linux-vanilla-dev \
        linux-headers \
    && apk add --no-cache \
        bash \
        ca-certificates \
        # g++ required for circusd's use of cython
        g++ \
        net-tools \
        nginx \
        openssl \
        python \
    && python /opt/Proximation/get-pip.py \
    && pip install --no-cache-dir -U pip \
    && pip install -U --no-cache-dir -r /opt/Proximation/requirements.txt \
    && rm /opt/Proximation/get-pip.py \
    && apk del build-dependencies

EXPOSE 80 443

ENTRYPOINT ["circusd"]
CMD ["/opt/Proximation/circus.ini"]

