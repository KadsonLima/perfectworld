#!/bin/bash

envsubst < /home/authd.conf.tmpl \
         > /home/authd.conf
envsubst < /home/table.xml.tmpl \
         > /home/table.xml
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone && \
    dpkg-reconfigure -f noninteractive tzdata

exec "$@"
