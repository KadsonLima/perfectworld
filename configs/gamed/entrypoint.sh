#!/bin/sh
set -eu

envsubst < /home/gmserver.conf.tmpl \
         > /home/gmserver.conf
ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone && \
    dpkg-reconfigure -f noninteractive tzdata

exec "$@"
