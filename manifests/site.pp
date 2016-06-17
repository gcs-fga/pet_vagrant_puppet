
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
  exec { 'psql':
    user => "postgres",
    command => "/usr/bin/createuser pet",
    path => "/home/pet",
    unless => "/usr/bin/psql postgres -tAc \"SELECT 1 FROM pg_roles WHERE rolname='pet'\" | /bin/grep -q 1"
  }
}
