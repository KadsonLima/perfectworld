#!/bin/bash

envsubst < /home/gmserver.conf.tmpl \
         > /home/gmserver.conf
chmod -R 755 /home
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone && \
    dpkg-reconfigure -f noninteractive tzdata

exec "$@"
