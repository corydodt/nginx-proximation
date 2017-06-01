# vim:set ft=dockerfile:
FROM alpine:3.5

RUN mkdir -p /usr/share/nginx/html /run/nginx /opt/Proximation
ENV PYTHONPATH=/opt/Proximation
WORKDIR /opt/Proximation

COPY ./requirements.txt \
     ./circus.ini \
    /opt/Proximation/

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
        coreutils \
        # g++ required for circusd's use of cython
        g++ \
        net-tools \
        nginx \
        openssl \
        python \
    && python -m ensurepip \
    && pip install -U --no-cache-dir -r /opt/Proximation/requirements.txt \
    && apk del build-dependencies

COPY ./http.conf.in \
     ./proximation.py \
    /opt/Proximation/

EXPOSE 80 443

ENTRYPOINT ["stdbuf", "-oL", "circusd"]
CMD ["/opt/Proximation/circus.ini"]

