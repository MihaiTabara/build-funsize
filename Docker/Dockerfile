# Use the latest Ubuntu
FROM ubuntu:latest
MAINTAINER "Anhad Jai Singh"
# Open port 5000 for Flask
EXPOSE 5000
RUN DEBIAN_FRONTEND=noninteractive apt-get update --allow-unauthenticated
RUN DEBIAN_FRONTEND=noninteractive apt-get install --allow-unauthenticated -y python-all python-dev python-virtualenv python-pip git curl wget perl
#
# Create tooling dir
RUN mkdir -p /perma/tools
# All this is one line because shell env isn't maintained across "RUN" calls
RUN git clone https://github.com/MihaiTabara/build-funsize /app;
WORKDIR /app
ENV C_FORCE_ROOT true

RUN python setup.py develop
CMD "/app/docker_init.sh"
