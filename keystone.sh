#!/bin/bash

keystone service-create --name traffic --type network --description 'Openstack Traffic Control'

keystone endpoint-create --region RegionOne --service-id  serviceid --publicrul "http://192.168.96.51:9898/$(tenand_id)s" --internalurl "http://192.168.96.51:9898/$(tenand_id)s"
                              --adminurl "http://192.168.96.51:9898/$(tenand_id)s"

keystone user-create --name=traffic --pass='password' --email=example@com --tenant-id=