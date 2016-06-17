
package { [
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

  service {"postgresql":
    ensure => running,
    enable => true,
    hasrestart => true,
  }

  exec { "creating tables":
    command => "/vagrant/pet-update -c -nc",
    user => "pet",
    unless => "/usr/bin/psql pet -tAc \"SELECT 1 FROM team\" | /bin/grep -q 1",
    path => "/",
  }
}
