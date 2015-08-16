# Dockerfile for Package Entropy Tracker http://pet.alioth.debian.org
#
# Copyright 2015, Simó Albert i Beltran <sim6@probeta.net>
#
# Permission to use, copy, modify, and/or distribute this software for any
# purpose with or without fee is hereby granted, provided that the above
# copyright notice and this permission notice appear in all copies.
#
# THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
# WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
# MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
# ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
# WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
# ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
# OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.

FROM debian
MAINTAINER Simó Albert i Beltran
ENV DEBIAN_FRONTEND noninteractive

RUN apt-get update
RUN apt-get upgrade -y
RUN apt-get install -y \
	postgresql-9.4 \
	postgresql-9.4-debversion \
	python-argparse python-debian \
	python-debianbts \
	python-inotifyx \
	python-paste \
	python-psycopg2 \
	python-pyramid \
	python-sqlalchemy \
	python-subversion \
	python-pip \
	wget

# Waiting for python-pyramid-chameleon package: https://bugs.debian.org/cgi-bin/bugreport.cgi?bug=785048
RUN pip install pyramid_chameleon

RUN useradd pet

COPY ./ /srv/pet/
WORKDIR /srv/pet/

RUN echo "port = 5435" >> /etc/postgresql/9.4/main/postgresql.conf
RUN sed -i -e "1ihost pet pet 127.0.0.1/32 trust" /etc/postgresql/9.4/main/pg_hba.conf

RUN service postgresql start \
	&& su postgres -c "createuser --createdb pet" \
	&& su pet -c "createdb pet" \
	&& su postgres -c "psql pet < /usr/share/postgresql/9.4/contrib/debversion.sql" \
	&& echo "127.0.0.1 bmdb1.debian.org" >> /etc/hosts \
	&& su pet -c "/srv/pet/pet-update -c" \
	&& su pet -c "psql pet --command \"INSERT INTO team (name, maintainer, url) VALUES ('pkg-perl', 'Debian Perl Group <pkg-perl-maintainers@lists.alioth.debian.org>', 'http://pkg-perl.alioth.debian.org/'); INSERT INTO repository (name, type, root, web_root, team_id) VALUES ('git','git','https://pet.alioth.debian.org/pet2-data/pkg-perl/git-pkg-perl-packages.json','http://anonscm.debian.org/gitweb/?p=pkg-perl/packages', 1); INSERT INTO package (name, repository_id) VALUES ('clive', 1); INSERT INTO archive (name, url, web_root) VALUES ('debian', 'http://cdn.debian.net/debian', 'http://packages.qa.debian.org/'); INSERT INTO suite (archive_id, name) VALUES (1, 'unstable');\""

CMD service postgresql start && echo "127.0.0.1 bmdb1.debian.org" >> /etc/hosts && su pet -c /srv/pet/pet-serve
EXPOSE 8080
