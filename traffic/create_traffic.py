# encoding: utf-8

import MySQLdb

def main():
    username = raw_input('input username:')
    password = raw_input('input password:')

    db = MySQLdb.connect("localhost", username, password, 'nova')

    cursor = db.cursor()
 #   cursor.execute('drop table if exists tfilter')
    tfilter_sql = '''create table tqdisc(
                                        id int not null,
                                        classid int,
                                        handle int,
                                        ip varchar(25),
                                        flowid varchar(10),
                                        prio int )'''
    
    cursor.execute(tfilter_sql)
    
 #   cursor.execute('drop table if exists tqdisc')
    
    tqdisc_sql = '''create table tfilter(
                                          id int not null,
                                          instanceid varchar(50),
                                          classid varchar(20),
                                          host varchar(20),
                                          band int,
                                          prio int)'''
    
    cursor.execute(tqdisc_sql)
    
    db.commit()

    db.close()


if __name__ == '__main__':
    main()