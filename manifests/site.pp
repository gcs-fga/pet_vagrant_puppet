
package { [
  'python',
  'vim',
  'vagrant',
  'python-pip',
  'postgresql-9.4',
  'postgresql-9.4-debversion',
  'python-argparse',
  'python-debian',
  'python-debianbts',
  'python-inotifyx',
  'python-paste',
  'python-psycopg2',
  'python-pyramid',
  'python-sqlalchemy',
  'python-subversion',
]:
  ensure => present,
}
package { 'pyramid_chameleon':
  provider => pip,
  ensure =>present,
}

include user
class user{
  user { 'pet':
    ensure     => present,
    shell      => '/bin/bash',
    home       => '/home/pet',
  }

  file { 'postgresql conf':
    path => '/etc/postgresql/9.4/main/postgresql.conf',
    ensure => file,
    content => template("/tmp/vagrant-puppet-4/manifests/files/postgresql.conf"),
  }

  file { 'pg_hba conf':
    path => '/etc/postgresql/9.4/main/pg_hba.conf',
    ensure => file,
    content => template("/tmp/vagrant-puppet-4/manifests/files/pg_hba.conf"),
  }

  exec { 'psql create user':
    user => "postgres",
    command => "/usr/bin/createuser pet",
    path => "/home/pet",
    unless => "/usr/bin/psql postgres -tAc \"SELECT 1 FROM pg_roles WHERE rolname='pet'\" | /bin/grep -q 1"
  }

  exec { 'create db pet':
    user => "postgres",
    command => "/usr/bin/createdb -O pet pet",
    path => "/home/pet",
    unless => "/usr/bin/psql -lqt | /usr/bin/cut -d \| -f 1 | /bin/grep -qw pet",
  }

  exec { 'implements deb version':
    user => "postgres",
    command => "/usr/bin/psql pet < /usr/share/postgresql/9.4/contrib/debversion.sql",
    path => "/home/pet",
  }

  file { 'hosts file':
    path => "/etc/hosts",
    ensure => file,
    content => template("/tmp/vagrant-puppet-4/manifests/files/hosts"),
  }

  service {"postgresql":
    ensure => running,
    enable => true,
    hasrestart => true,
  }

  exec { "creating tables":
    command => "/usr/bin/python /vagrant/pet-update -c -nc",
    user => "pet",
    unless => "/usr/bin/psql pet -tAc \"SELECT 1 FROM team\" | /bin/grep -q 1",
    path => "/",
  }

  exec{ "insert a team on bd":
    command => "/usr/bin/psql pet --command \"INSERT INTO team (name, maintainer, url) VALUES ('pkg-perl', 'Debian Perl Group <pkg-perl-maintainers@lists.alioth.debian.org>', 'http://pkg-perl.alioth.debian.org/');\"",
    user => "pet",
    unless => "/usr/bin/psql pet -tAc \"SELECT * FROM team WHERE name='pkg-perl'\" | /bin/grep -q 'pkg-perl'",
  }
  exec{ "database insert repository table":
    command => "/usr/bin/psql pet --command \"INSERT INTO repository (name, type, root, web_root, team_id) VALUES ('git','git','https://pet.alioth.debian.org/pet2-data/pkg-perl/git-pkg-perl-packages.json','http://anonscm.debian.org/gitweb/?p=pkg-perl/packages', 1);\"",
    user => "pet",
    unless => "/usr/bin/psql pet -tAc \"SELECT * FROM repository WHERE name='git'\" | /bin/grep -q 'git'",
  }
  exec{ "database insert package table":
    command => "/usr/bin/psql pet --command \"INSERT INTO package (name, repository_id) VALUES ('clive', 1);\"",
    user => "pet",
    unless => "/usr/bin/psql pet -tAc \"SELECT * FROM package WHERE name='clive'\" | /bin/grep -q 'clive'"
  }

  exec{ "database insert archive table":
    command => "/usr/bin/psql pet --command \"INSERT INTO archive (name, url, web_root) VALUES ('debian', 'http://cdn.debian.net/debian', 'http://packages.qa.debian.org/');\"",
    user => "pet",
    unless => "/usr/bin/psql pet -tAc \"SELECT * FROM archive WHERE name='debian'\" | /bin/grep -q 'debian'",
  }
  exec{ "database insert suite table":
    command => "/usr/bin/psql pet --command \"INSERT INTO suite (archive_id, name) VALUES (1, 'unstable');\"",
    user => "pet",
    unless => "/usr/bin/psql pet -tAc \"SELECT * FROM suite WHERE name='unstable'\" | /bin/grep -q 'unstable'",
  }
}
