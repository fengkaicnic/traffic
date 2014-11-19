# encoding: utf-8

import MySQLdb

def main():
    username = raw_input('input username:')
    password = raw_input('input password:')

    db = MySQLdb.connect("localhost", username, password, 'nova')

    cursor = db.cursor()
 #   cursor.execute('drop table if exists tfilter')
    tfilter_sql = '''create table tfilter(
                                        id int not null primary key auto_increment,
                                        created_at datetime default null,
                                        updated_at datetime default null,
                                        deleted_at datetime default null,
                                        deleted varchar(36),
                                        classid varchar(10),
                                        handle int,
                                        ip varchar(25),
                                        flowid varchar(10),
                                        prio int )'''
    
    cursor.execute(tfilter_sql)
    
 #   cursor.execute('drop table if exists tqdisc')
    
    tqdisc_sql = '''create table tqdisc(
                                          id int not null primary key auto_increment,
                                          created_at datetime default null,
                                          updated_at datetime default null,
                                          deleted_at datetime default null,
                                          deleted varchar(36),
                                          instanceid varchar(50),
                                          classid varchar(20),
                                          ip varchar(25),
                                          host varchar(20),
                                          band varchar(15),
                                          prio int)'''
    
    cursor.execute(tqdisc_sql)
    
    db.commit()

    db.close()


if __name__ == '__main__':
    main()