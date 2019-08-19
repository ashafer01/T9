FROM ubuntu:18.04

RUN mkdir /home/user && useradd -px user && chown -R user: /home/user && apt-get -y update && apt-get -y install gnupg2 debconf-utils
COPY locales-selections /tmp/locales-selections
RUN debconf-set-selections /tmp/locales-selections && apt-get -y install locales
VOLUME /home

CMD ["sleep", "infinity"]
