#!/bin/sh
set -eu

envsubst < /home/authd.conf.tmpl \
         > /home/authd.conf
envsubst < /home/table.xml.tmpl \
         > /home/table.xml
ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone && \
    dpkg-reconfigure -f noninteractive tzdata

exec "$@"
