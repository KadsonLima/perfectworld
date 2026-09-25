#!/bin/sh
set -eu

envsubst < /home/logservice.conf.tmpl \
         > /home/logservice.conf
ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone && \
    dpkg-reconfigure -f noninteractive tzdata

exec "$@"
