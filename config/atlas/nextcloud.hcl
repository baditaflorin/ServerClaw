Notice: This Atlas edition lacks support for features such as checkpoints,
testing, down migrations, and more. Additionally, advanced database objects such as views,
triggers, and stored procedures are not supported. To read more: https://atlasgo.io/community-edition

To install the non-community version of Atlas, use the following command:

	curl -sSf https://atlasgo.sh | sh

Or, visit the website to see all installation options:

	https://atlasgo.io/docs#installation

table "oc_accounts" {
  schema = schema.public
  column "uid" {
    null    = false
    type    = character_varying(64)
    default = ""
  }
  column "data" {
    null    = false
    type    = text
    default = ""
  }
  primary_key {
    columns = [column.uid]
  }
}
table "oc_accounts_data" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "uid" {
    null = false
    type = character_varying(64)
  }
  column "name" {
    null = false
    type = character_varying(64)
  }
  column "value" {
    null    = true
    type    = character_varying(255)
    default = ""
  }
  primary_key {
    columns = [column.id]
  }
  index "accounts_data_name" {
    columns = [column.name]
  }
  index "accounts_data_uid" {
    columns = [column.uid]
  }
  index "accounts_data_value" {
    columns = [column.value]
  }
}
table "oc_activity" {
  schema = schema.public
  column "activity_id" {
    null = false
    type = bigserial
  }
  column "timestamp" {
    null    = false
    type    = integer
    default = 0
  }
  column "priority" {
    null    = false
    type    = integer
    default = 0
  }
  column "type" {
    null    = true
    type    = character_varying(255)
    default = sql("NULL::character varying")
  }
  column "user" {
    null    = true
    type    = character_varying(64)
    default = sql("NULL::character varying")
  }
  column "affecteduser" {
    null = false
    type = character_varying(64)
  }
  column "app" {
    null = false
    type = character_varying(32)
  }
  column "subject" {
    null = false
    type = character_varying(255)
  }
  column "subjectparams" {
    null = false
    type = text
  }
  column "message" {
    null    = true
    type    = character_varying(255)
    default = sql("NULL::character varying")
  }
  column "messageparams" {
    null = true
    type = text
  }
  column "file" {
    null    = true
    type    = character_varying(4000)
    default = sql("NULL::character varying")
  }
  column "link" {
    null    = true
    type    = character_varying(4000)
    default = sql("NULL::character varying")
  }
  column "object_type" {
    null    = true
    type    = character_varying(255)
    default = sql("NULL::character varying")
  }
  column "object_id" {
    null    = false
    type    = bigint
    default = 0
  }
  primary_key {
    columns = [column.activity_id]
  }
  index "activity_filter" {
    columns = [column.affecteduser, column.type, column.app, column.timestamp]
  }
  index "activity_filter_by" {
    columns = [column.affecteduser, column.user, column.timestamp]
  }
  index "activity_object" {
    columns = [column.object_type, column.object_id]
  }
  index "activity_object_user" {
    columns = [column.affecteduser, column.object_type, column.object_id, column.timestamp]
  }
  index "activity_user_time" {
    columns = [column.affecteduser, column.timestamp]
  }
}
table "oc_activity_mq" {
  schema = schema.public
  column "mail_id" {
    null = false
    type = bigserial
  }
  column "amq_timestamp" {
    null    = false
    type    = integer
    default = 0
  }
  column "amq_latest_send" {
    null    = false
    type    = integer
    default = 0
  }
  column "amq_type" {
    null = false
    type = character_varying(255)
  }
  column "amq_affecteduser" {
    null = false
    type = character_varying(64)
  }
  column "amq_appid" {
    null = false
    type = character_varying(32)
  }
  column "amq_subject" {
    null = false
    type = character_varying(255)
  }
  column "amq_subjectparams" {
    null = true
    type = text
  }
  column "object_type" {
    null    = true
    type    = character_varying(255)
    default = sql("NULL::character varying")
  }
  column "object_id" {
    null    = false
    type    = bigint
    default = 0
  }
  primary_key {
    columns = [column.mail_id]
  }
  index "amp_latest_send_time" {
    columns = [column.amq_latest_send]
  }
  index "amp_timestamp_time" {
    columns = [column.amq_timestamp]
  }
  index "amp_user" {
    columns = [column.amq_affecteduser]
  }
}
table "oc_addressbookchanges" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "uri" {
    null    = true
    type    = character_varying(255)
    default = sql("NULL::character varying")
  }
  column "synctoken" {
    null    = false
    type    = integer
    default = 1
  }
  column "addressbookid" {
    null = false
    type = bigint
  }
  column "operation" {
    null = false
    type = smallint
  }
  column "created_at" {
    null    = false
    type    = integer
    default = 0
  }
  primary_key {
    columns = [column.id]
  }
  index "addressbookid_synctoken" {
    columns = [column.addressbookid, column.synctoken]
  }
}
table "oc_addressbooks" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "principaluri" {
    null    = true
    type    = character_varying(255)
    default = sql("NULL::character varying")
  }
  column "displayname" {
    null    = true
    type    = character_varying(255)
    default = sql("NULL::character varying")
  }
  column "uri" {
    null    = true
    type    = character_varying(255)
    default = sql("NULL::character varying")
  }
  column "description" {
    null    = true
    type    = character_varying(255)
    default = sql("NULL::character varying")
  }
  column "synctoken" {
    null    = false
    type    = integer
    default = 1
  }
  primary_key {
    columns = [column.id]
  }
  index "addressbook_index" {
    unique  = true
    columns = [column.principaluri, column.uri]
  }
}
table "oc_appconfig" {
  schema = schema.public
  column "appid" {
    null    = false
    type    = character_varying(32)
    default = ""
  }
  column "configkey" {
    null    = false
    type    = character_varying(64)
    default = ""
  }
  column "configvalue" {
    null = true
    type = text
  }
  column "type" {
    null    = false
    type    = integer
    default = 2
  }
  column "lazy" {
    null    = false
    type    = smallint
    default = 0
  }
  primary_key {
    columns = [column.appid, column.configkey]
  }
  index "ac_lazy_i" {
    columns = [column.lazy]
  }
}
table "oc_appconfig_ex" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "appid" {
    null = false
    type = character_varying(32)
  }
  column "configkey" {
    null = false
    type = character_varying(64)
  }
  column "configvalue" {
    null = true
    type = text
  }
  column "sensitive" {
    null    = false
    type    = smallint
    default = 0
  }
  primary_key {
    columns = [column.id]
  }
  index "appconfig_ex__configkey" {
    columns = [column.configkey]
  }
  index "appconfig_ex__idx" {
    unique  = true
    columns = [column.appid, column.configkey]
  }
}
table "oc_authorized_groups" {
  schema = schema.public
  column "id" {
    null = false
    type = serial
  }
  column "group_id" {
    null = false
    type = character_varying(200)
  }
  column "class" {
    null = false
    type = character_varying(200)
  }
  primary_key {
    columns = [column.id]
  }
  index "admindel_groupid_idx" {
    columns = [column.group_id]
  }
}
table "oc_authtoken" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "uid" {
    null    = false
    type    = character_varying(64)
    default = ""
  }
  column "login_name" {
    null    = false
    type    = character_varying(255)
    default = ""
  }
  column "password" {
    null = true
    type = text
  }
  column "name" {
    null    = false
    type    = text
    default = ""
  }
  column "token" {
    null    = false
    type    = character_varying(200)
    default = ""
  }
  column "type" {
    null    = true
    type    = smallint
    default = 0
  }
  column "remember" {
    null    = true
    type    = smallint
    default = 0
  }
  column "last_activity" {
    null    = true
    type    = integer
    default = 0
  }
  column "last_check" {
    null    = true
    type    = integer
    default = 0
  }
  column "scope" {
    null = true
    type = text
  }
  column "expires" {
    null = true
    type = integer
  }
  column "private_key" {
    null = true
    type = text
  }
  column "public_key" {
    null = true
    type = text
  }
  column "version" {
    null    = false
    type    = smallint
    default = 1
  }
  column "password_invalid" {
    null    = true
    type    = boolean
    default = false
  }
  column "password_hash" {
    null    = true
    type    = character_varying(255)
    default = sql("NULL::character varying")
  }
  primary_key {
    columns = [column.id]
  }
  index "authtoken_last_activity_idx" {
    columns = [column.last_activity]
  }
  index "authtoken_token_index" {
    unique  = true
    columns = [column.token]
  }
  index "authtoken_uid_index" {
    columns = [column.uid]
  }
}
table "oc_bruteforce_attempts" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "action" {
    null    = false
    type    = character_varying(64)
    default = ""
  }
  column "occurred" {
    null    = false
    type    = integer
    default = 0
  }
  column "ip" {
    null    = false
    type    = character_varying(255)
    default = ""
  }
  column "subnet" {
    null    = false
    type    = character_varying(255)
    default = ""
  }
  column "metadata" {
    null    = false
    type    = character_varying(255)
    default = ""
  }
  primary_key {
    columns = [column.id]
  }
  index "bruteforce_attempts_ip" {
    columns = [column.ip]
  }
  index "bruteforce_attempts_subnet" {
    columns = [column.subnet]
  }
}
table "oc_calendar_invitations" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "uid" {
    null = false
    type = character_varying(512)
  }
  column "recurrenceid" {
    null    = true
    type    = character_varying(255)
    default = sql("NULL::character varying")
  }
  column "attendee" {
    null = false
    type = character_varying(255)
  }
  column "organizer" {
    null = false
    type = character_varying(255)
  }
  column "sequence" {
    null = true
    type = bigint
  }
  column "token" {
    null = false
    type = character_varying(60)
  }
  column "expiration" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  index "calendar_invitation_tokens" {
    columns = [column.token]
  }
}
table "oc_calendar_reminders" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "calendar_id" {
    null = false
    type = bigint
  }
  column "object_id" {
    null = false
    type = bigint
  }
  column "is_recurring" {
    null = true
    type = smallint
  }
  column "uid" {
    null = false
    type = character_varying(512)
  }
  column "recurrence_id" {
    null = true
    type = bigint
  }
  column "is_recurrence_exception" {
    null = false
    type = smallint
  }
  column "event_hash" {
    null = false
    type = character_varying(255)
  }
  column "alarm_hash" {
    null = false
    type = character_varying(255)
  }
  column "type" {
    null = false
    type = character_varying(255)
  }
  column "is_relative" {
    null = false
    type = smallint
  }
  column "notification_date" {
    null = false
    type = bigint
  }
  column "is_repeat_based" {
    null = false
    type = smallint
  }
  primary_key {
    columns = [column.id]
  }
  index "calendar_reminder_objid" {
    columns = [column.object_id]
  }
  index "calendar_reminder_uidrec" {
    columns = [column.uid, column.recurrence_id]
  }
}
table "oc_calendar_resources" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "backend_id" {
    null    = true
    type    = character_varying(64)
    default = sql("NULL::character varying")
  }
  column "resource_id" {
    null    = true
    type    = character_varying(64)
    default = sql("NULL::character varying")
  }
  column "email" {
    null    = true
    type    = character_varying(255)
    default = sql("NULL::character varying")
  }
  column "displayname" {
    null    = true
    type    = character_varying(255)
    default = sql("NULL::character varying")
  }
  column "group_restrictions" {
    null    = true
    type    = character_varying(4000)
    default = sql("NULL::character varying")
  }
  primary_key {
    columns = [column.id]
  }
  index "calendar_resources_bkdrsc" {
    columns = [column.backend_id, column.resource_id]
  }
  index "calendar_resources_email" {
    columns = [column.email]
  }
  index "calendar_resources_name" {
    columns = [column.displayname]
  }
}
table "oc_calendar_resources_md" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "resource_id" {
    null = false
    type = bigint
  }
  column "key" {
    null = false
    type = character_varying(255)
  }
  column "value" {
    null    = true
    type    = character_varying(4000)
    default = sql("NULL::character varying")
  }
  primary_key {
    columns = [column.id]
  }
  index "calendar_resources_md_idk" {
    columns = [column.resource_id, column.key]
  }
}
table "oc_calendar_rooms" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "backend_id" {
    null    = true
    type    = character_varying(64)
    default = sql("NULL::character varying")
  }
  column "resource_id" {
    null    = true
    type    = character_varying(64)
    default = sql("NULL::character varying")
  }
  column "email" {
    null    = true
    type    = character_varying(255)
    default = sql("NULL::character varying")
  }
  column "displayname" {
    null    = true
    type    = character_varying(255)
    default = sql("NULL::character varying")
  }
  column "group_restrictions" {
    null    = true
    type    = character_varying(4000)
    default = sql("NULL::character varying")
  }
  primary_key {
    columns = [column.id]
  }
  index "calendar_rooms_bkdrsc" {
    columns = [column.backend_id, column.resource_id]
  }
  index "calendar_rooms_email" {
    columns = [column.email]
  }
  index "calendar_rooms_name" {
    columns = [column.displayname]
  }
}
table "oc_calendar_rooms_md" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "room_id" {
    null = false
    type = bigint
  }
  column "key" {
    null = false
    type = character_varying(255)
  }
  column "value" {
    null    = true
    type    = character_varying(4000)
    default = sql("NULL::character varying")
  }
  primary_key {
    columns = [column.id]
  }
  index "calendar_rooms_md_idk" {
    columns = [column.room_id, column.key]
  }
}
table "oc_calendarchanges" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "uri" {
    null    = true
    type    = character_varying(255)
    default = sql("NULL::character varying")
  }
  column "synctoken" {
    null    = false
    type    = integer
    default = 1
  }
  column "calendarid" {
    null = false
    type = bigint
  }
  column "operation" {
    null = false
    type = smallint
  }
  column "calendartype" {
    null    = false
    type    = integer
    default = 0
  }
  column "created_at" {
    null    = false
    type    = integer
    default = 0
  }
  primary_key {
    columns = [column.id]
  }
  index "calid_type_synctoken" {
    columns = [column.calendarid, column.calendartype, column.synctoken]
  }
}
table "oc_calendarobjects" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "calendardata" {
    null = true
    type = bytea
  }
  column "uri" {
    null    = true
    type    = character_varying(255)
    default = sql("NULL::character varying")
  }
  column "calendarid" {
    null = false
    type = bigint
  }
  column "lastmodified" {
    null = true
    type = integer
  }
  column "etag" {
    null    = true
    type    = character_varying(32)
    default = sql("NULL::character varying")
  }
  column "size" {
    null = false
    type = bigint
  }
  column "componenttype" {
    null    = true
    type    = character_varying(8)
    default = sql("NULL::character varying")
  }
  column "firstoccurence" {
    null = true
    type = bigint
  }
  column "lastoccurence" {
    null = true
    type = bigint
  }
  column "uid" {
    null    = true
    type    = character_varying(512)
    default = sql("NULL::character varying")
  }
  column "classification" {
    null    = true
    type    = integer
    default = 0
  }
  column "calendartype" {
    null    = false
    type    = integer
    default = 0
  }
  column "deleted_at" {
    null = true
    type = integer
  }
  primary_key {
    columns = [column.id]
  }
  index "calobj_clssfction_index" {
    columns = [column.classification]
  }
  index "calobjects_by_uid_index" {
    unique  = true
    columns = [column.calendarid, column.calendartype, column.uid]
  }
  index "calobjects_index" {
    unique  = true
    columns = [column.calendarid, column.calendartype, column.uri]
  }
}
table "oc_calendarobjects_props" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "calendarid" {
    null    = false
    type    = bigint
    default = 0
  }
  column "objectid" {
    null    = false
    type    = bigint
    default = 0
  }
  column "name" {
    null    = true
    type    = character_varying(64)
    default = sql("NULL::character varying")
  }
  column "parameter" {
    null    = true
    type    = character_varying(64)
    default = sql("NULL::character varying")
  }
  column "value" {
    null    = true
    type    = character_varying(255)
    default = sql("NULL::character varying")
  }
  column "calendartype" {
    null    = false
    type    = integer
    default = 0
  }
  primary_key {
    columns = [column.id]
  }
  index "calendarobject_calid_index" {
    columns = [column.calendarid, column.calendartype]
  }
  index "calendarobject_index" {
    columns = [column.objectid, column.calendartype]
  }
  index "calendarobject_name_index" {
    columns = [column.name, column.calendartype]
  }
  index "calendarobject_value_index" {
    columns = [column.value, column.calendartype]
  }
}
table "oc_calendars" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "principaluri" {
    null    = true
    type    = character_varying(255)
    default = sql("NULL::character varying")
  }
  column "displayname" {
    null    = true
    type    = character_varying(255)
    default = sql("NULL::character varying")
  }
  column "uri" {
    null    = true
    type    = character_varying(255)
    default = sql("NULL::character varying")
  }
  column "synctoken" {
    null    = false
    type    = integer
    default = 1
  }
  column "description" {
    null    = true
    type    = character_varying(255)
    default = sql("NULL::character varying")
  }
  column "calendarorder" {
    null    = false
    type    = integer
    default = 0
  }
  column "calendarcolor" {
    null    = true
    type    = character_varying(255)
    default = sql("NULL::character varying")
  }
  column "timezone" {
    null = true
    type = text
  }
  column "components" {
    null    = true
    type    = character_varying(64)
    default = sql("NULL::character varying")
  }
  column "transparent" {
    null    = false
    type    = smallint
    default = 0
  }
  column "deleted_at" {
    null = true
    type = integer
  }
  primary_key {
    columns = [column.id]
  }
  index "calendars_index" {
    unique  = true
    columns = [column.principaluri, column.uri]
  }
  index "cals_princ_del_idx" {
    columns = [column.principaluri, column.deleted_at]
  }
}
table "oc_calendars_federated" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "display_name" {
    null = false
    type = character_varying(255)
  }
  column "color" {
    null    = true
    type    = character_varying(7)
    default = sql("NULL::character varying")
  }
  column "uri" {
    null = false
    type = character_varying(255)
  }
  column "principaluri" {
    null = false
    type = character_varying(255)
  }
  column "remote_url" {
    null = false
    type = character_varying(255)
  }
  column "token" {
    null = false
    type = character_varying(255)
  }
  column "sync_token" {
    null    = false
    type    = integer
    default = 0
  }
  column "last_sync" {
    null = true
    type = bigint
  }
  column "shared_by" {
    null = false
    type = character_varying(255)
  }
  column "shared_by_display_name" {
    null = false
    type = character_varying(255)
  }
  column "components" {
    null = false
    type = character_varying(255)
  }
  column "permissions" {
    null = false
    type = integer
  }
  primary_key {
    columns = [column.id]
  }
  index "fedcals_last_sync_index" {
    columns = [column.last_sync]
  }
  index "fedcals_uris_index" {
    columns = [column.principaluri, column.uri]
  }
}
table "oc_calendarsubscriptions" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "uri" {
    null    = true
    type    = character_varying(255)
    default = sql("NULL::character varying")
  }
  column "principaluri" {
    null    = true
    type    = character_varying(255)
    default = sql("NULL::character varying")
  }
  column "displayname" {
    null    = true
    type    = character_varying(100)
    default = sql("NULL::character varying")
  }
  column "refreshrate" {
    null    = true
    type    = character_varying(10)
    default = sql("NULL::character varying")
  }
  column "calendarorder" {
    null    = false
    type    = integer
    default = 0
  }
  column "calendarcolor" {
    null    = true
    type    = character_varying(255)
    default = sql("NULL::character varying")
  }
  column "striptodos" {
    null = true
    type = smallint
  }
  column "stripalarms" {
    null = true
    type = smallint
  }
  column "stripattachments" {
    null = true
    type = smallint
  }
  column "lastmodified" {
    null = true
    type = integer
  }
  column "synctoken" {
    null    = false
    type    = integer
    default = 1
  }
  column "source" {
    null = true
    type = text
  }
  primary_key {
    columns = [column.id]
  }
  index "calsub_index" {
    unique  = true
    columns = [column.principaluri, column.uri]
  }
}
table "oc_cards" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "addressbookid" {
    null    = false
    type    = bigint
    default = 0
  }
  column "carddata" {
    null = true
    type = bytea
  }
  column "uri" {
    null    = true
    type    = character_varying(255)
    default = sql("NULL::character varying")
  }
  column "lastmodified" {
    null = true
    type = bigint
  }
  column "etag" {
    null    = true
    type    = character_varying(32)
    default = sql("NULL::character varying")
  }
  column "size" {
    null = false
    type = bigint
  }
  column "uid" {
    null    = true
    type    = character_varying(255)
    default = sql("NULL::character varying")
  }
  primary_key {
    columns = [column.id]
  }
  index "cards_abiduri" {
    columns = [column.addressbookid, column.uri]
  }
}
table "oc_cards_properties" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "addressbookid" {
    null    = false
    type    = bigint
    default = 0
  }
  column "cardid" {
    null    = false
    type    = bigint
    default = 0
  }
  column "name" {
    null    = true
    type    = character_varying(64)
    default = sql("NULL::character varying")
  }
  column "value" {
    null    = true
    type    = character_varying(255)
    default = sql("NULL::character varying")
  }
  column "preferred" {
    null    = false
    type    = integer
    default = 1
  }
  primary_key {
    columns = [column.id]
  }
  index "card_contactid_index" {
    columns = [column.cardid]
  }
  index "card_name_index" {
    columns = [column.name]
  }
  index "card_value_index" {
    columns = [column.value]
  }
  index "cards_prop_abid_name_value" {
    columns = [column.addressbookid, column.name, column.value]
  }
}
table "oc_circles_circle" {
  schema = schema.public
  column "id" {
    null = false
    type = serial
  }
  column "unique_id" {
    null = false
    type = character_varying(31)
  }
  column "name" {
    null = false
    type = character_varying(127)
  }
  column "display_name" {
    null    = true
    type    = character_varying(255)
    default = ""
  }
  column "sanitized_name" {
    null    = true
    type    = character_varying(127)
    default = ""
  }
  column "instance" {
    null    = true
    type    = character_varying(255)
    default = ""
  }
  column "config" {
    null = true
    type = integer
  }
  column "source" {
    null = true
    type = integer
  }
  column "settings" {
    null = true
    type = text
  }
  column "description" {
    null = true
    type = text
  }
  column "creation" {
    null    = true
    type    = timestamp(0)
    default = sql("NULL::timestamp without time zone")
  }
  column "contact_addressbook" {
    null = true
    type = integer
  }
  column "contact_groupname" {
    null    = true
    type    = character_varying(127)
    default = sql("NULL::character varying")
  }
  primary_key {
    columns = [column.id]
  }
  index "dname" {
    columns = [column.display_name]
  }
  index "idx_8195f5484230b1de" {
    columns = [column.instance]
  }
  index "idx_8195f5485f8a7f73" {
    columns = [column.source]
  }
  index "idx_8195f548c317b362" {
    columns = [column.sanitized_name]
  }
  index "idx_8195f548d48a2f7c" {
    columns = [column.config]
  }
  index "uniq_8195f548e3c68343" {
    unique  = true
    columns = [column.unique_id]
  }
}
table "oc_circles_event" {
  schema = schema.public
  column "token" {
    null = false
    type = character_varying(63)
  }
  column "instance" {
    null = false
    type = character_varying(255)
  }
  column "event" {
    null = true
    type = text
  }
  column "result" {
    null = true
    type = text
  }
  column "interface" {
    null    = false
    type    = integer
    default = 0
  }
  column "severity" {
    null = true
    type = integer
  }
  column "retry" {
    null = true
    type = integer
  }
  column "status" {
    null = true
    type = integer
  }
  column "updated" {
    null    = true
    type    = timestamp(0)
    default = sql("NULL::timestamp without time zone")
  }
  column "creation" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.token, column.instance]
  }
}
table "oc_circles_member" {
  schema = schema.public
  column "id" {
    null = false
    type = serial
  }
  column "single_id" {
    null    = true
    type    = character_varying(31)
    default = sql("NULL::character varying")
  }
  column "circle_id" {
    null = false
    type = character_varying(31)
  }
  column "member_id" {
    null    = true
    type    = character_varying(31)
    default = sql("NULL::character varying")
  }
  column "user_id" {
    null = false
    type = character_varying(127)
  }
  column "user_type" {
    null    = false
    type    = smallint
    default = 1
  }
  column "instance" {
    null    = true
    type    = character_varying(255)
    default = ""
  }
  column "invited_by" {
    null    = true
    type    = character_varying(31)
    default = sql("NULL::character varying")
  }
  column "level" {
    null = false
    type = smallint
  }
  column "status" {
    null    = true
    type    = character_varying(15)
    default = sql("NULL::character varying")
  }
  column "note" {
    null = true
    type = text
  }
  column "cached_name" {
    null    = true
    type    = character_varying(255)
    default = ""
  }
  column "cached_update" {
    null    = true
    type    = timestamp(0)
    default = sql("NULL::timestamp without time zone")
  }
  column "contact_id" {
    null    = true
    type    = character_varying(127)
    default = sql("NULL::character varying")
  }
  column "contact_meta" {
    null = true
    type = text
  }
  column "joined" {
    null    = true
    type    = timestamp(0)
    default = sql("NULL::timestamp without time zone")
  }
  primary_key {
    columns = [column.id]
  }
  index "circles_member_cisi" {
    columns = [column.circle_id, column.single_id]
  }
  index "circles_member_cisiuiutil" {
    columns = [column.circle_id, column.single_id, column.user_id, column.user_type, column.instance, column.level]
  }
  index "idx_25c66a49e7a1254a" {
    columns = [column.contact_id]
  }
}
table "oc_circles_membership" {
  schema = schema.public
  column "circle_id" {
    null = false
    type = character_varying(31)
  }
  column "single_id" {
    null = false
    type = character_varying(31)
  }
  column "level" {
    null = false
    type = integer
  }
  column "inheritance_first" {
    null = false
    type = character_varying(31)
  }
  column "inheritance_last" {
    null = false
    type = character_varying(31)
  }
  column "inheritance_depth" {
    null = false
    type = integer
  }
  column "inheritance_path" {
    null = false
    type = text
  }
  primary_key {
    columns = [column.single_id, column.circle_id]
  }
  index "circles_membership_ifilci" {
    columns = [column.inheritance_first, column.inheritance_last, column.circle_id]
  }
  index "idx_8fc816eae7c1d92b" {
    columns = [column.single_id]
  }
}
table "oc_circles_mount" {
  schema = schema.public
  column "id" {
    null = false
    type = serial
  }
  column "mount_id" {
    null = false
    type = character_varying(31)
  }
  column "circle_id" {
    null = false
    type = character_varying(31)
  }
  column "single_id" {
    null = false
    type = character_varying(31)
  }
  column "token" {
    null    = true
    type    = character_varying(63)
    default = sql("NULL::character varying")
  }
  column "parent" {
    null = true
    type = integer
  }
  column "mountpoint" {
    null = true
    type = text
  }
  column "mountpoint_hash" {
    null    = true
    type    = character_varying(64)
    default = sql("NULL::character varying")
  }
  column "remote" {
    null    = true
    type    = character_varying(255)
    default = ""
  }
  column "remote_id" {
    null    = false
    type    = integer
    default = 0
  }
  primary_key {
    columns = [column.id]
  }
  index "circles_mount_cimipt" {
    columns = [column.circle_id, column.mount_id, column.parent, column.token]
  }
  index "m_sid_rmt_rid" {
    columns = [column.circle_id, column.remote, column.remote_id]
  }
}
table "oc_circles_mountpoint" {
  schema = schema.public
  column "id" {
    null = false
    type = serial
  }
  column "mount_id" {
    null = false
    type = character_varying(31)
  }
  column "single_id" {
    null = false
    type = character_varying(31)
  }
  column "mountpoint" {
    null = true
    type = text
  }
  column "mountpoint_hash" {
    null    = true
    type    = character_varying(64)
    default = sql("NULL::character varying")
  }
  primary_key {
    columns = [column.id]
  }
  index "circles_mountpoint_ms" {
    columns = [column.mount_id, column.single_id]
  }
  index "mp_sid_hash" {
    unique  = true
    columns = [column.single_id, column.mountpoint_hash]
  }
}
table "oc_circles_remote" {
  schema = schema.public
  column "id" {
    null = false
    type = serial
  }
  column "type" {
    null    = false
    type    = character_varying(15)
    default = "Unknown"
  }
  column "interface" {
    null    = false
    type    = integer
    default = 0
  }
  column "uid" {
    null    = true
    type    = character_varying(20)
    default = sql("NULL::character varying")
  }
  column "instance" {
    null    = true
    type    = character_varying(127)
    default = sql("NULL::character varying")
  }
  column "href" {
    null    = true
    type    = character_varying(254)
    default = sql("NULL::character varying")
  }
  column "item" {
    null = true
    type = text
  }
  column "creation" {
    null    = true
    type    = timestamp(0)
    default = sql("NULL::timestamp without time zone")
  }
  primary_key {
    columns = [column.id]
  }
  index "idx_f94ef8334f8e741" {
    columns = [column.href]
  }
  index "idx_f94ef83539b0606" {
    columns = [column.uid]
  }
  index "uniq_f94ef834230b1de" {
    unique  = true
    columns = [column.instance]
  }
}
table "oc_circles_share_lock" {
  schema = schema.public
  column "id" {
    null = false
    type = serial
  }
  column "item_id" {
    null = false
    type = character_varying(31)
  }
  column "circle_id" {
    null = false
    type = character_varying(31)
  }
  column "instance" {
    null = false
    type = character_varying(127)
  }
  primary_key {
    columns = [column.id]
  }
  index "uniq_337f52f8126f525e70ee2ff6" {
    unique  = true
    columns = [column.item_id, column.circle_id]
  }
}
table "oc_circles_token" {
  schema = schema.public
  column "id" {
    null = false
    type = serial
  }
  column "share_id" {
    null = true
    type = integer
  }
  column "circle_id" {
    null    = true
    type    = character_varying(31)
    default = sql("NULL::character varying")
  }
  column "single_id" {
    null    = true
    type    = character_varying(31)
    default = sql("NULL::character varying")
  }
  column "member_id" {
    null    = true
    type    = character_varying(31)
    default = sql("NULL::character varying")
  }
  column "token" {
    null    = true
    type    = character_varying(31)
    default = sql("NULL::character varying")
  }
  column "password" {
    null    = true
    type    = character_varying(127)
    default = sql("NULL::character varying")
  }
  column "accepted" {
    null = true
    type = integer
  }
  primary_key {
    columns = [column.id]
  }
  index "sicisimit" {
    unique  = true
    columns = [column.share_id, column.circle_id, column.single_id, column.member_id, column.token]
  }
}
table "oc_collres_accesscache" {
  schema = schema.public
  column "user_id" {
    null = false
    type = character_varying(64)
  }
  column "collection_id" {
    null    = false
    type    = bigint
    default = 0
  }
  column "resource_type" {
    null    = false
    type    = character_varying(64)
    default = ""
  }
  column "resource_id" {
    null    = false
    type    = character_varying(64)
    default = ""
  }
  column "access" {
    null    = true
    type    = boolean
    default = false
  }
  primary_key {
    columns = [column.user_id, column.collection_id, column.resource_type, column.resource_id]
  }
  index "collres_user_res" {
    columns = [column.user_id, column.resource_type, column.resource_id]
  }
}
table "oc_collres_collections" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "name" {
    null = false
    type = character_varying(64)
  }
  primary_key {
    columns = [column.id]
  }
}
table "oc_collres_resources" {
  schema = schema.public
  column "collection_id" {
    null = false
    type = bigint
  }
  column "resource_type" {
    null = false
    type = character_varying(64)
  }
  column "resource_id" {
    null = false
    type = character_varying(64)
  }
  primary_key {
    columns = [column.collection_id, column.resource_type, column.resource_id]
  }
}
table "oc_comments" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "parent_id" {
    null    = false
    type    = bigint
    default = 0
  }
  column "topmost_parent_id" {
    null    = false
    type    = bigint
    default = 0
  }
  column "children_count" {
    null    = false
    type    = integer
    default = 0
  }
  column "actor_type" {
    null    = false
    type    = character_varying(64)
    default = ""
  }
  column "actor_id" {
    null    = false
    type    = character_varying(64)
    default = ""
  }
  column "message" {
    null = true
    type = text
  }
  column "verb" {
    null    = true
    type    = character_varying(64)
    default = sql("NULL::character varying")
  }
  column "creation_timestamp" {
    null    = true
    type    = timestamp(0)
    default = sql("NULL::timestamp without time zone")
  }
  column "latest_child_timestamp" {
    null    = true
    type    = timestamp(0)
    default = sql("NULL::timestamp without time zone")
  }
  column "object_type" {
    null    = false
    type    = character_varying(64)
    default = ""
  }
  column "object_id" {
    null    = false
    type    = character_varying(64)
    default = ""
  }
  column "reference_id" {
    null    = true
    type    = character_varying(64)
    default = sql("NULL::character varying")
  }
  column "reactions" {
    null    = true
    type    = character_varying(4000)
    default = sql("NULL::character varying")
  }
  column "expire_date" {
    null    = true
    type    = timestamp(0)
    default = sql("NULL::timestamp without time zone")
  }
  column "meta_data" {
    null    = true
    type    = text
    default = ""
  }
  primary_key {
    columns = [column.id]
  }
  index "comments_actor_index" {
    columns = [column.actor_type, column.actor_id]
  }
  index "comments_object_index" {
    columns = [column.object_type, column.object_id, column.creation_timestamp]
  }
  index "comments_parent_id_index" {
    columns = [column.parent_id]
  }
  index "comments_topmost_parent_id_idx" {
    columns = [column.topmost_parent_id]
  }
  index "expire_date" {
    columns = [column.expire_date]
  }
}
table "oc_comments_read_markers" {
  schema = schema.public
  column "user_id" {
    null    = false
    type    = character_varying(64)
    default = ""
  }
  column "object_type" {
    null    = false
    type    = character_varying(64)
    default = ""
  }
  column "object_id" {
    null    = false
    type    = character_varying(64)
    default = ""
  }
  column "marker_datetime" {
    null    = true
    type    = timestamp(0)
    default = sql("NULL::timestamp without time zone")
  }
  primary_key {
    columns = [column.user_id, column.object_type, column.object_id]
  }
  index "comments_marker_object_index" {
    columns = [column.object_type, column.object_id]
  }
}
table "oc_dav_absence" {
  schema = schema.public
  column "id" {
    null = false
    type = serial
  }
  column "user_id" {
    null = false
    type = character_varying(64)
  }
  column "first_day" {
    null = false
    type = character_varying(10)
  }
  column "last_day" {
    null = false
    type = character_varying(10)
  }
  column "status" {
    null = false
    type = character_varying(100)
  }
  column "message" {
    null = false
    type = text
  }
  column "replacement_user_id" {
    null    = true
    type    = character_varying(64)
    default = ""
  }
  column "replacement_user_display_name" {
    null    = true
    type    = character_varying(64)
    default = ""
  }
  primary_key {
    columns = [column.id]
  }
  index "dav_absence_uid_idx" {
    unique  = true
    columns = [column.user_id]
  }
}
table "oc_dav_cal_proxy" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "owner_id" {
    null = false
    type = character_varying(64)
  }
  column "proxy_id" {
    null = false
    type = character_varying(64)
  }
  column "permissions" {
    null = true
    type = integer
  }
  primary_key {
    columns = [column.id]
  }
  index "dav_cal_proxy_ipid" {
    columns = [column.proxy_id]
  }
  index "dav_cal_proxy_uidx" {
    unique  = true
    columns = [column.owner_id, column.proxy_id, column.permissions]
  }
}
table "oc_dav_shares" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "principaluri" {
    null    = true
    type    = character_varying(255)
    default = sql("NULL::character varying")
  }
  column "type" {
    null    = true
    type    = character_varying(255)
    default = sql("NULL::character varying")
  }
  column "access" {
    null = true
    type = smallint
  }
  column "resourceid" {
    null = false
    type = bigint
  }
  column "publicuri" {
    null    = true
    type    = character_varying(255)
    default = sql("NULL::character varying")
  }
  column "token" {
    null    = true
    type    = character_varying(255)
    default = sql("NULL::character varying")
  }
  primary_key {
    columns = [column.id]
  }
  index "dav_shares_index" {
    unique  = true
    columns = [column.principaluri, column.resourceid, column.type, column.publicuri]
  }
  index "dav_shares_resourceid_access" {
    columns = [column.resourceid, column.access]
  }
  index "dav_shares_resourceid_type" {
    columns = [column.resourceid, column.type]
  }
}
table "oc_direct_edit" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "editor_id" {
    null = false
    type = character_varying(64)
  }
  column "token" {
    null = false
    type = character_varying(64)
  }
  column "file_id" {
    null = false
    type = bigint
  }
  column "user_id" {
    null    = true
    type    = character_varying(64)
    default = sql("NULL::character varying")
  }
  column "share_id" {
    null = true
    type = bigint
  }
  column "timestamp" {
    null = false
    type = bigint
  }
  column "accessed" {
    null    = true
    type    = boolean
    default = false
  }
  column "file_path" {
    null    = true
    type    = character_varying(4000)
    default = sql("NULL::character varying")
  }
  primary_key {
    columns = [column.id]
  }
  index "direct_edit_timestamp" {
    columns = [column.timestamp]
  }
  index "idx_4d5afeca5f37a13b" {
    columns = [column.token]
  }
}
table "oc_directlink" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "user_id" {
    null    = true
    type    = character_varying(64)
    default = sql("NULL::character varying")
  }
  column "file_id" {
    null = false
    type = bigint
  }
  column "token" {
    null    = true
    type    = character_varying(60)
    default = sql("NULL::character varying")
  }
  column "expiration" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  index "directlink_expiration_idx" {
    columns = [column.expiration]
  }
  index "directlink_token_idx" {
    columns = [column.token]
  }
}
table "oc_ex_apps" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "appid" {
    null = false
    type = character_varying(32)
  }
  column "version" {
    null = false
    type = character_varying(32)
  }
  column "name" {
    null = false
    type = character_varying(64)
  }
  column "daemon_config_name" {
    null    = false
    type    = character_varying(64)
    default = "0"
  }
  column "port" {
    null = false
    type = smallint
  }
  column "secret" {
    null = false
    type = character_varying(256)
  }
  column "status" {
    null = false
    type = json
  }
  column "enabled" {
    null    = false
    type    = smallint
    default = 0
  }
  column "created_time" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  index "ex_apps__appid" {
    unique  = true
    columns = [column.appid]
  }
  index "ex_apps_c_port__idx" {
    unique  = true
    columns = [column.daemon_config_name, column.port]
  }
}
table "oc_ex_apps_daemons" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "name" {
    null = false
    type = character_varying(64)
  }
  column "display_name" {
    null = false
    type = character_varying(255)
  }
  column "accepts_deploy_id" {
    null = false
    type = character_varying(64)
  }
  column "protocol" {
    null = false
    type = character_varying(32)
  }
  column "host" {
    null = false
    type = character_varying(255)
  }
  column "deploy_config" {
    null = false
    type = json
  }
  primary_key {
    columns = [column.id]
  }
  index "ex_apps_daemons__name" {
    unique  = true
    columns = [column.name]
  }
}
table "oc_ex_apps_routes" {
  schema = schema.public
  column "id" {
    null = false
    type = serial
  }
  column "appid" {
    null = false
    type = character_varying(32)
  }
  column "url" {
    null = false
    type = character_varying(512)
  }
  column "verb" {
    null = false
    type = character_varying(64)
  }
  column "access_level" {
    null    = false
    type    = integer
    default = 0
  }
  column "headers_to_exclude" {
    null    = true
    type    = character_varying(512)
    default = sql("NULL::character varying")
  }
  column "bruteforce_protection" {
    null    = true
    type    = character_varying(512)
    default = sql("NULL::character varying")
  }
  primary_key {
    columns = [column.id]
  }
  index "ex_apps_routes_appid" {
    columns = [column.appid]
  }
}
table "oc_ex_deploy_options" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "appid" {
    null = false
    type = character_varying(32)
  }
  column "type" {
    null = false
    type = character_varying(32)
  }
  column "value" {
    null = false
    type = json
  }
  primary_key {
    columns = [column.id]
  }
  index "deploy_options__idx" {
    unique  = true
    columns = [column.appid, column.type]
  }
}
table "oc_ex_occ_commands" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "appid" {
    null = false
    type = character_varying(32)
  }
  column "name" {
    null = false
    type = character_varying(64)
  }
  column "description" {
    null    = true
    type    = character_varying(255)
    default = sql("NULL::character varying")
  }
  column "hidden" {
    null    = false
    type    = smallint
    default = 0
  }
  column "arguments" {
    null = false
    type = json
  }
  column "options" {
    null = false
    type = json
  }
  column "usages" {
    null = false
    type = json
  }
  column "execute_handler" {
    null = false
    type = character_varying(410)
  }
  primary_key {
    columns = [column.id]
  }
  index "ex_occ_commands__idx" {
    unique  = true
    columns = [column.appid, column.name]
  }
}
table "oc_ex_settings_forms" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "appid" {
    null = false
    type = character_varying(32)
  }
  column "formid" {
    null = false
    type = character_varying(64)
  }
  column "scheme" {
    null = false
    type = json
  }
  primary_key {
    columns = [column.id]
  }
  index "ex_settings_forms__idx" {
    unique  = true
    columns = [column.appid, column.formid]
  }
}
table "oc_ex_task_processing" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "app_id" {
    null = false
    type = character_varying(32)
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "display_name" {
    null = false
    type = character_varying(255)
  }
  column "task_type" {
    null = false
    type = character_varying(255)
  }
  column "custom_task_type" {
    null = true
    type = text
  }
  column "provider" {
    null = false
    type = text
  }
  primary_key {
    columns = [column.id]
  }
  index "task_processing_idx" {
    unique  = true
    columns = [column.app_id, column.name, column.task_type]
  }
}
table "oc_ex_ui_files_actions" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "appid" {
    null = false
    type = character_varying(32)
  }
  column "name" {
    null = false
    type = character_varying(64)
  }
  column "display_name" {
    null = false
    type = character_varying(64)
  }
  column "mime" {
    null    = false
    type    = text
    default = "file"
  }
  column "permissions" {
    null = false
    type = character_varying(255)
  }
  column "order" {
    null    = false
    type    = bigint
    default = 0
  }
  column "icon" {
    null    = true
    type    = character_varying(255)
    default = ""
  }
  column "action_handler" {
    null = false
    type = character_varying(64)
  }
  column "version" {
    null    = false
    type    = character_varying(64)
    default = "1.0"
  }
  primary_key {
    columns = [column.id]
  }
  index "ex_ui_files_actions__idx" {
    unique  = true
    columns = [column.appid, column.name]
  }
}
table "oc_ex_ui_scripts" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "appid" {
    null = false
    type = character_varying(32)
  }
  column "type" {
    null = false
    type = character_varying(16)
  }
  column "name" {
    null = false
    type = character_varying(32)
  }
  column "path" {
    null = false
    type = character_varying(410)
  }
  column "after_app_id" {
    null    = true
    type    = character_varying(32)
    default = sql("NULL::character varying")
  }
  primary_key {
    columns = [column.id]
  }
  index "ui_script__idx" {
    unique  = true
    columns = [column.appid, column.type, column.name, column.path]
  }
}
table "oc_ex_ui_states" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "appid" {
    null = false
    type = character_varying(32)
  }
  column "type" {
    null = false
    type = character_varying(16)
  }
  column "name" {
    null = false
    type = character_varying(32)
  }
  column "key" {
    null = false
    type = character_varying(64)
  }
  column "value" {
    null = false
    type = json
  }
  primary_key {
    columns = [column.id]
  }
  index "ui_state__idx" {
    unique  = true
    columns = [column.appid, column.type, column.name, column.key]
  }
}
table "oc_ex_ui_styles" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "appid" {
    null = false
    type = character_varying(32)
  }
  column "type" {
    null = false
    type = character_varying(16)
  }
  column "name" {
    null = false
    type = character_varying(32)
  }
  column "path" {
    null = false
    type = character_varying(410)
  }
  primary_key {
    columns = [column.id]
  }
  index "ui_style__idx" {
    unique  = true
    columns = [column.appid, column.type, column.name, column.path]
  }
}
table "oc_ex_ui_top_menu" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "appid" {
    null = false
    type = character_varying(32)
  }
  column "name" {
    null = false
    type = character_varying(32)
  }
  column "display_name" {
    null = false
    type = character_varying(32)
  }
  column "icon" {
    null    = true
    type    = character_varying(255)
    default = ""
  }
  column "admin_required" {
    null    = false
    type    = smallint
    default = 0
  }
  primary_key {
    columns = [column.id]
  }
  index "ui_top_menu__idx" {
    unique  = true
    columns = [column.appid, column.name]
  }
}
table "oc_federated_invites" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "user_id" {
    null = false
    type = character_varying(64)
  }
  column "recipient_provider" {
    null    = true
    type    = character_varying(2083)
    default = sql("NULL::character varying")
  }
  column "recipient_user_id" {
    null    = true
    type    = character_varying(1024)
    default = sql("NULL::character varying")
  }
  column "recipient_name" {
    null    = true
    type    = character_varying(1024)
    default = sql("NULL::character varying")
  }
  column "recipient_email" {
    null    = true
    type    = character_varying(320)
    default = sql("NULL::character varying")
  }
  column "token" {
    null = false
    type = character_varying(60)
  }
  column "accepted" {
    null    = true
    type    = boolean
    default = false
  }
  column "created_at" {
    null = false
    type = bigint
  }
  column "expired_at" {
    null = true
    type = bigint
  }
  column "accepted_at" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  unique "uniq_a2c17d5a5f37a13b" {
    columns = [column.token]
  }
}
table "oc_federated_reshares" {
  schema = schema.public
  column "share_id" {
    null = false
    type = bigint
  }
  column "remote_id" {
    null    = true
    type    = character_varying(255)
    default = ""
  }
  primary_key {
    columns = [column.share_id]
  }
}
table "oc_file_locks" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "lock" {
    null    = false
    type    = integer
    default = 0
  }
  column "key" {
    null = false
    type = character_varying(64)
  }
  column "ttl" {
    null    = false
    type    = integer
    default = -1
  }
  primary_key {
    columns = [column.id]
  }
  index "lock_key_index" {
    unique  = true
    columns = [column.key]
  }
  index "lock_ttl_index" {
    columns = [column.ttl]
  }
}
table "oc_filecache" {
  schema = schema.public
  column "fileid" {
    null = false
    type = bigserial
  }
  column "storage" {
    null    = false
    type    = bigint
    default = 0
  }
  column "path" {
    null    = true
    type    = character_varying(4000)
    default = sql("NULL::character varying")
  }
  column "path_hash" {
    null    = false
    type    = character_varying(32)
    default = ""
  }
  column "parent" {
    null    = false
    type    = bigint
    default = 0
  }
  column "name" {
    null    = true
    type    = character_varying(250)
    default = sql("NULL::character varying")
  }
  column "mimetype" {
    null    = false
    type    = bigint
    default = 0
  }
  column "mimepart" {
    null    = false
    type    = bigint
    default = 0
  }
  column "size" {
    null    = false
    type    = bigint
    default = 0
  }
  column "mtime" {
    null    = false
    type    = bigint
    default = 0
  }
  column "storage_mtime" {
    null    = false
    type    = bigint
    default = 0
  }
  column "encrypted" {
    null    = false
    type    = integer
    default = 0
  }
  column "unencrypted_size" {
    null    = false
    type    = bigint
    default = 0
  }
  column "etag" {
    null    = true
    type    = character_varying(40)
    default = sql("NULL::character varying")
  }
  column "permissions" {
    null    = true
    type    = integer
    default = 0
  }
  column "checksum" {
    null    = true
    type    = character_varying(255)
    default = sql("NULL::character varying")
  }
  primary_key {
    columns = [column.fileid]
  }
  index "fs_mtime" {
    columns = [column.mtime]
  }
  index "fs_name_hash" {
    columns = [column.name]
  }
  index "fs_parent" {
    columns = [column.parent]
  }
  index "fs_parent_name_hash" {
    columns = [column.parent, column.name]
  }
  index "fs_size" {
    columns = [column.size]
  }
  index "fs_storage_mimepart" {
    columns = [column.storage, column.mimepart]
  }
  index "fs_storage_mimetype" {
    columns = [column.storage, column.mimetype]
  }
  index "fs_storage_path_hash" {
    unique  = true
    columns = [column.storage, column.path_hash]
  }
  index "fs_storage_size" {
    columns = [column.storage, column.size, column.fileid]
  }
}
table "oc_filecache_extended" {
  schema = schema.public
  column "fileid" {
    null = false
    type = bigint
  }
  column "metadata_etag" {
    null    = true
    type    = character_varying(40)
    default = sql("NULL::character varying")
  }
  column "creation_time" {
    null    = false
    type    = bigint
    default = 0
  }
  column "upload_time" {
    null    = false
    type    = bigint
    default = 0
  }
  primary_key {
    columns = [column.fileid]
  }
  index "fce_ctime_idx" {
    columns = [column.creation_time]
  }
  index "fce_utime_idx" {
    columns = [column.upload_time]
  }
}
table "oc_files_metadata" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "file_id" {
    null = false
    type = bigint
  }
  column "json" {
    null = false
    type = text
  }
  column "sync_token" {
    null = false
    type = character_varying(15)
  }
  column "last_update" {
    null = false
    type = timestamp(0)
  }
  primary_key {
    columns = [column.id]
  }
  index "files_meta_fileid" {
    unique  = true
    columns = [column.file_id]
  }
}
table "oc_files_metadata_index" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "file_id" {
    null = false
    type = bigint
  }
  column "meta_key" {
    null    = true
    type    = character_varying(31)
    default = sql("NULL::character varying")
  }
  column "meta_value_string" {
    null    = true
    type    = character_varying(63)
    default = sql("NULL::character varying")
  }
  column "meta_value_int" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  index "f_meta_index" {
    columns = [column.file_id, column.meta_key, column.meta_value_string]
  }
  index "f_meta_index_i" {
    columns = [column.file_id, column.meta_key, column.meta_value_int]
  }
}
table "oc_files_reminders" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "user_id" {
    null = false
    type = character_varying(64)
  }
  column "file_id" {
    null = false
    type = bigint
  }
  column "due_date" {
    null = false
    type = timestamp(0)
  }
  column "updated_at" {
    null = false
    type = timestamp(0)
  }
  column "created_at" {
    null = false
    type = timestamp(0)
  }
  column "notified" {
    null    = true
    type    = boolean
    default = false
  }
  primary_key {
    columns = [column.id]
  }
  index "reminders_uniq_idx" {
    unique  = true
    columns = [column.user_id, column.file_id, column.due_date]
  }
}
table "oc_files_trash" {
  schema = schema.public
  column "auto_id" {
    null = false
    type = bigserial
  }
  column "id" {
    null    = false
    type    = character_varying(250)
    default = ""
  }
  column "user" {
    null    = false
    type    = character_varying(64)
    default = ""
  }
  column "timestamp" {
    null    = false
    type    = character_varying(12)
    default = ""
  }
  column "location" {
    null    = false
    type    = character_varying(512)
    default = ""
  }
  column "type" {
    null    = true
    type    = character_varying(4)
    default = sql("NULL::character varying")
  }
  column "mime" {
    null    = true
    type    = character_varying(255)
    default = sql("NULL::character varying")
  }
  column "deleted_by" {
    null    = true
    type    = character_varying(64)
    default = sql("NULL::character varying")
  }
  primary_key {
    columns = [column.auto_id]
  }
  index "id_index" {
    columns = [column.id]
  }
  index "timestamp_index" {
    columns = [column.timestamp]
  }
  index "user_index" {
    columns = [column.user]
  }
}
table "oc_files_versions" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "file_id" {
    null = false
    type = bigint
  }
  column "timestamp" {
    null = false
    type = bigint
  }
  column "size" {
    null = false
    type = bigint
  }
  column "mimetype" {
    null = false
    type = bigint
  }
  column "metadata" {
    null = false
    type = json
  }
  primary_key {
    columns = [column.id]
  }
  index "files_versions_uniq_index" {
    unique  = true
    columns = [column.file_id, column.timestamp]
  }
}
table "oc_flow_checks" {
  schema = schema.public
  column "id" {
    null = false
    type = serial
  }
  column "class" {
    null    = false
    type    = character_varying(256)
    default = ""
  }
  column "operator" {
    null    = false
    type    = character_varying(16)
    default = ""
  }
  column "value" {
    null = true
    type = text
  }
  column "hash" {
    null    = false
    type    = character_varying(32)
    default = ""
  }
  primary_key {
    columns = [column.id]
  }
  index "flow_unique_hash" {
    unique  = true
    columns = [column.hash]
  }
}
table "oc_flow_operations" {
  schema = schema.public
  column "id" {
    null = false
    type = serial
  }
  column "class" {
    null    = false
    type    = character_varying(256)
    default = ""
  }
  column "name" {
    null    = true
    type    = character_varying(256)
    default = ""
  }
  column "checks" {
    null = true
    type = text
  }
  column "operation" {
    null = true
    type = text
  }
  column "entity" {
    null    = false
    type    = character_varying(256)
    default = "OCA\\WorkflowEngine\\Entity\\File"
  }
  column "events" {
    null    = false
    type    = text
    default = "[]"
  }
  primary_key {
    columns = [column.id]
  }
}
table "oc_flow_operations_scope" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "operation_id" {
    null    = false
    type    = integer
    default = 0
  }
  column "type" {
    null    = false
    type    = integer
    default = 0
  }
  column "value" {
    null    = true
    type    = character_varying(64)
    default = ""
  }
  primary_key {
    columns = [column.id]
  }
  index "flow_unique_scope" {
    unique  = true
    columns = [column.operation_id, column.type, column.value]
  }
}
table "oc_group_admin" {
  schema = schema.public
  column "gid" {
    null    = false
    type    = character_varying(64)
    default = ""
  }
  column "uid" {
    null    = false
    type    = character_varying(64)
    default = ""
  }
  primary_key {
    columns = [column.gid, column.uid]
  }
  index "group_admin_uid" {
    columns = [column.uid]
  }
}
table "oc_group_user" {
  schema = schema.public
  column "gid" {
    null    = false
    type    = character_varying(64)
    default = ""
  }
  column "uid" {
    null    = false
    type    = character_varying(64)
    default = ""
  }
  primary_key {
    columns = [column.gid, column.uid]
  }
  index "gu_uid_index" {
    columns = [column.uid]
  }
}
table "oc_groups" {
  schema = schema.public
  column "gid" {
    null    = false
    type    = character_varying(64)
    default = ""
  }
  column "displayname" {
    null    = false
    type    = character_varying(255)
    default = "name"
  }
  primary_key {
    columns = [column.gid]
  }
}
table "oc_jobs" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
  }
  column "class" {
    null    = false
    type    = character_varying(255)
    default = ""
  }
  column "argument" {
    null    = false
    type    = text
    default = ""
  }
  column "last_run" {
    null    = true
    type    = integer
    default = 0
  }
  column "last_checked" {
    null    = true
    type    = integer
    default = 0
  }
  column "reserved_at" {
    null    = true
    type    = integer
    default = 0
  }
  column "execution_duration" {
    null    = true
    type    = integer
    default = 0
  }
  column "argument_hash" {
    null    = true
    type    = character_varying(64)
    default = sql("NULL::character varying")
  }
  column "time_sensitive" {
    null    = false
    type    = smallint
    default = 1
  }
  primary_key {
    columns = [column.id]
  }
  index "job_argument_hash" {
    columns = [column.class, column.argument_hash]
  }
  index "job_class_index" {
    columns = [column.class]
  }
  index "job_lastcheck_reserved" {
    columns = [column.last_checked, column.reserved_at]
  }
  index "jobs_time_sensitive" {
    columns = [column.time_sensitive]
  }
}
table "oc_known_users" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "known_to" {
    null = false
    type = character_varying(255)
  }
  column "known_user" {
    null = false
    type = character_varying(255)
  }
  primary_key {
    columns = [column.id]
  }
  index "ku_known_to" {
    columns = [column.known_to]
  }
  index "ku_known_user" {
    columns = [column.known_user]
  }
}
table "oc_login_flow_v2" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "timestamp" {
    null = false
    type = bigint
  }
  column "started" {
    null    = false
    type    = smallint
    default = 0
  }
  column "poll_token" {
    null = false
    type = character_varying(255)
  }
  column "login_token" {
    null = false
    type = character_varying(255)
  }
  column "public_key" {
    null = false
    type = text
  }
  column "private_key" {
    null = false
    type = text
  }
  column "client_name" {
    null = false
    type = character_varying(255)
  }
  column "login_name" {
    null    = true
    type    = character_varying(255)
    default = sql("NULL::character varying")
  }
  column "server" {
    null    = true
    type    = character_varying(255)
    default = sql("NULL::character varying")
  }
  column "app_password" {
    null    = true
    type    = character_varying(1024)
    default = sql("NULL::character varying")
  }
  primary_key {
    columns = [column.id]
  }
  index "login_token" {
    unique  = true
    columns = [column.login_token]
  }
  index "poll_token" {
    unique  = true
    columns = [column.poll_token]
  }
  index "timestamp" {
    columns = [column.timestamp]
  }
}
table "oc_migrations" {
  schema = schema.public
  column "app" {
    null = false
    type = character_varying(255)
  }
  column "version" {
    null = false
    type = character_varying(255)
  }
  primary_key {
    columns = [column.app, column.version]
  }
}
table "oc_mimetypes" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "mimetype" {
    null    = false
    type    = character_varying(255)
    default = ""
  }
  primary_key {
    columns = [column.id]
  }
  index "mimetype_id_index" {
    unique  = true
    columns = [column.mimetype]
  }
}
table "oc_mounts" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "storage_id" {
    null = false
    type = bigint
  }
  column "root_id" {
    null = false
    type = bigint
  }
  column "user_id" {
    null = false
    type = character_varying(64)
  }
  column "mount_point" {
    null = false
    type = character_varying(4000)
  }
  column "mount_id" {
    null = true
    type = bigint
  }
  column "mount_provider_class" {
    null    = true
    type    = character_varying(128)
    default = sql("NULL::character varying")
  }
  column "mount_point_hash" {
    null = false
    type = character_varying(32)
  }
  primary_key {
    columns = [column.id]
  }
  index "mount_user_storage" {
    columns = [column.storage_id, column.user_id]
  }
  index "mounts_class_index" {
    columns = [column.mount_provider_class]
  }
  index "mounts_mount_id_index" {
    columns = [column.mount_id]
  }
  index "mounts_root_index" {
    columns = [column.root_id]
  }
  index "mounts_storage_index" {
    columns = [column.storage_id]
  }
  index "mounts_user_root_path_index" {
    unique  = true
    columns = [column.user_id, column.root_id, column.mount_point_hash]
  }
}
table "oc_notifications" {
  schema = schema.public
  column "notification_id" {
    null = false
    type = serial
  }
  column "app" {
    null = false
    type = character_varying(32)
  }
  column "user" {
    null = false
    type = character_varying(64)
  }
  column "timestamp" {
    null    = false
    type    = integer
    default = 0
  }
  column "object_type" {
    null = false
    type = character_varying(64)
  }
  column "object_id" {
    null = false
    type = character_varying(64)
  }
  column "subject" {
    null = false
    type = character_varying(64)
  }
  column "subject_parameters" {
    null = true
    type = text
  }
  column "message" {
    null    = true
    type    = character_varying(64)
    default = sql("NULL::character varying")
  }
  column "message_parameters" {
    null = true
    type = text
  }
  column "link" {
    null    = true
    type    = character_varying(4000)
    default = sql("NULL::character varying")
  }
  column "icon" {
    null    = true
    type    = character_varying(4000)
    default = sql("NULL::character varying")
  }
  column "actions" {
    null = true
    type = text
  }
  primary_key {
    columns = [column.notification_id]
  }
  index "oc_notifications_app" {
    columns = [column.app]
  }
  index "oc_notifications_object" {
    columns = [column.object_type, column.object_id]
  }
  index "oc_notifications_timestamp" {
    columns = [column.timestamp]
  }
  index "oc_notifications_user" {
    columns = [column.user]
  }
}
table "oc_notifications_pushhash" {
  schema = schema.public
  column "id" {
    null = false
    type = serial
  }
  column "uid" {
    null = false
    type = character_varying(64)
  }
  column "token" {
    null    = false
    type    = integer
    default = 0
  }
  column "deviceidentifier" {
    null = false
    type = character_varying(128)
  }
  column "devicepublickey" {
    null = false
    type = character_varying(512)
  }
  column "devicepublickeyhash" {
    null = false
    type = character_varying(128)
  }
  column "pushtokenhash" {
    null = false
    type = character_varying(128)
  }
  column "proxyserver" {
    null = false
    type = character_varying(256)
  }
  column "apptype" {
    null    = false
    type    = character_varying(32)
    default = "unknown"
  }
  primary_key {
    columns = [column.id]
  }
  index "oc_npushhash_di" {
    columns = [column.deviceidentifier]
  }
  index "oc_npushhash_uid" {
    unique  = true
    columns = [column.uid, column.token]
  }
}
table "oc_notifications_settings" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "user_id" {
    null = false
    type = character_varying(64)
  }
  column "batch_time" {
    null    = false
    type    = integer
    default = 0
  }
  column "last_send_id" {
    null    = false
    type    = bigint
    default = 0
  }
  column "next_send_time" {
    null    = false
    type    = integer
    default = 0
  }
  primary_key {
    columns = [column.id]
  }
  index "notset_nextsend" {
    columns = [column.next_send_time]
  }
  index "notset_user" {
    unique  = true
    columns = [column.user_id]
  }
}
table "oc_oauth2_access_tokens" {
  schema = schema.public
  column "id" {
    null = false
    type = serial
  }
  column "token_id" {
    null = false
    type = integer
  }
  column "client_id" {
    null = false
    type = integer
  }
  column "hashed_code" {
    null = false
    type = character_varying(128)
  }
  column "encrypted_token" {
    null = false
    type = character_varying(786)
  }
  column "code_created_at" {
    null    = false
    type    = bigint
    default = 0
  }
  column "token_count" {
    null    = false
    type    = bigint
    default = 0
  }
  primary_key {
    columns = [column.id]
  }
  index "oauth2_access_client_id_idx" {
    columns = [column.client_id]
  }
  index "oauth2_access_hash_idx" {
    unique  = true
    columns = [column.hashed_code]
  }
  index "oauth2_tk_c_created_idx" {
    columns = [column.token_count, column.code_created_at]
  }
}
table "oc_oauth2_clients" {
  schema = schema.public
  column "id" {
    null = false
    type = serial
  }
  column "name" {
    null = false
    type = character_varying(64)
  }
  column "redirect_uri" {
    null = false
    type = character_varying(2000)
  }
  column "client_identifier" {
    null = false
    type = character_varying(64)
  }
  column "secret" {
    null = false
    type = character_varying(512)
  }
  primary_key {
    columns = [column.id]
  }
  index "oauth2_client_id_idx" {
    unique  = true
    columns = [column.client_identifier]
  }
}
table "oc_open_local_editor" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "user_id" {
    null = false
    type = character_varying(64)
  }
  column "path_hash" {
    null = false
    type = character_varying(64)
  }
  column "expiration_time" {
    null = false
    type = bigint
  }
  column "token" {
    null = false
    type = character_varying(128)
  }
  primary_key {
    columns = [column.id]
  }
  index "openlocal_user_path_token" {
    unique  = true
    columns = [column.user_id, column.path_hash, column.token]
  }
}
table "oc_photos_albums" {
  schema = schema.public
  column "album_id" {
    null = false
    type = bigserial
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "user" {
    null = false
    type = character_varying(255)
  }
  column "created" {
    null = false
    type = bigint
  }
  column "location" {
    null = false
    type = character_varying(255)
  }
  column "last_added_photo" {
    null = false
    type = bigint
  }
  column "filters" {
    null = true
    type = text
  }
  primary_key {
    columns = [column.album_id]
  }
  index "pa_user" {
    columns = [column.user]
  }
}
table "oc_photos_albums_collabs" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "album_id" {
    null = false
    type = bigint
  }
  column "collaborator_id" {
    null = false
    type = character_varying(64)
  }
  column "collaborator_type" {
    null = false
    type = integer
  }
  primary_key {
    columns = [column.id]
  }
  index "album_collabs_uniq_collab" {
    unique  = true
    columns = [column.album_id, column.collaborator_id, column.collaborator_type]
  }
}
table "oc_photos_albums_files" {
  schema = schema.public
  column "album_file_id" {
    null = false
    type = bigserial
  }
  column "album_id" {
    null = false
    type = bigint
  }
  column "file_id" {
    null = false
    type = bigint
  }
  column "added" {
    null = false
    type = bigint
  }
  column "owner" {
    null    = true
    type    = character_varying(64)
    default = sql("NULL::character varying")
  }
  primary_key {
    columns = [column.album_file_id]
  }
  index "paf_album_file" {
    unique  = true
    columns = [column.album_id, column.file_id]
  }
  index "paf_folder" {
    columns = [column.album_id]
  }
}
table "oc_preferences" {
  schema = schema.public
  column "userid" {
    null    = false
    type    = character_varying(64)
    default = ""
  }
  column "appid" {
    null    = false
    type    = character_varying(32)
    default = ""
  }
  column "configkey" {
    null    = false
    type    = character_varying(64)
    default = ""
  }
  column "configvalue" {
    null = true
    type = text
  }
  column "lazy" {
    null    = false
    type    = smallint
    default = 0
  }
  column "type" {
    null    = false
    type    = smallint
    default = 0
  }
  column "flags" {
    null    = false
    type    = integer
    default = 0
  }
  column "indexed" {
    null    = true
    type    = character_varying(64)
    default = ""
  }
  primary_key {
    columns = [column.userid, column.appid, column.configkey]
  }
  index "prefs_app_key_ind_fl_i" {
    columns = [column.appid, column.configkey, column.indexed, column.flags]
  }
  index "prefs_uid_lazy_i" {
    columns = [column.userid, column.lazy]
  }
}
table "oc_preferences_ex" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "userid" {
    null = false
    type = character_varying(64)
  }
  column "appid" {
    null = false
    type = character_varying(32)
  }
  column "configkey" {
    null = false
    type = character_varying(64)
  }
  column "configvalue" {
    null = true
    type = text
  }
  column "sensitive" {
    null    = false
    type    = smallint
    default = 0
  }
  primary_key {
    columns = [column.id]
  }
  index "preferences_ex__configkey" {
    columns = [column.configkey]
  }
  index "preferences_ex__idx" {
    unique  = true
    columns = [column.userid, column.appid, column.configkey]
  }
}
table "oc_preview_locations" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
  }
  column "bucket_name" {
    null = false
    type = character_varying(40)
  }
  column "object_store_name" {
    null = false
    type = character_varying(40)
  }
  primary_key {
    columns = [column.id]
  }
  index "unique_bucket_store" {
    unique  = true
    columns = [column.bucket_name, column.object_store_name]
  }
}
table "oc_preview_versions" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
  }
  column "file_id" {
    null = false
    type = bigint
  }
  column "version" {
    null    = false
    type    = character_varying(1024)
    default = ""
  }
  primary_key {
    columns = [column.id]
  }
}
table "oc_previews" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
  }
  column "file_id" {
    null = false
    type = bigint
  }
  column "storage_id" {
    null = false
    type = bigint
  }
  column "old_file_id" {
    null = true
    type = bigint
  }
  column "location_id" {
    null = true
    type = bigint
  }
  column "width" {
    null = false
    type = integer
  }
  column "height" {
    null = false
    type = integer
  }
  column "mimetype_id" {
    null = false
    type = integer
  }
  column "source_mimetype_id" {
    null = false
    type = integer
  }
  column "max" {
    null    = false
    type    = boolean
    default = false
  }
  column "cropped" {
    null    = false
    type    = boolean
    default = false
  }
  column "encrypted" {
    null    = false
    type    = boolean
    default = false
  }
  column "etag" {
    null = false
    type = character(40)
  }
  column "mtime" {
    null = false
    type = integer
  }
  column "size" {
    null = false
    type = integer
  }
  column "version_id" {
    null    = false
    type    = bigint
    default = -1
  }
  primary_key {
    columns = [column.id]
  }
  index "idx_67dc472793cb796c" {
    columns = [column.file_id]
  }
  index "previews_file_uniq_idx" {
    unique  = true
    columns = [column.file_id, column.width, column.height, column.mimetype_id, column.cropped, column.version_id]
  }
}
table "oc_privacy_admins" {
  schema = schema.public
  column "id" {
    null = false
    type = serial
  }
  column "displayname" {
    null    = false
    type    = character_varying(64)
    default = ""
  }
  primary_key {
    columns = [column.id]
  }
}
table "oc_profile_config" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "user_id" {
    null = false
    type = character_varying(64)
  }
  column "config" {
    null = false
    type = text
  }
  primary_key {
    columns = [column.id]
  }
  index "profile_config_user_id_idx" {
    unique  = true
    columns = [column.user_id]
  }
}
table "oc_properties" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "userid" {
    null    = false
    type    = character_varying(64)
    default = ""
  }
  column "propertypath" {
    null    = false
    type    = character_varying(255)
    default = ""
  }
  column "propertyname" {
    null    = false
    type    = character_varying(255)
    default = ""
  }
  column "propertyvalue" {
    null = false
    type = text
  }
  column "valuetype" {
    null    = true
    type    = smallint
    default = 1
  }
  primary_key {
    columns = [column.id]
  }
  index "properties_name_path_user" {
    columns = [column.propertyname, column.propertypath, column.userid]
  }
  index "properties_path_index" {
    columns = [column.userid, column.propertypath]
  }
  index "properties_pathonly_index" {
    columns = [column.propertypath]
  }
}
table "oc_ratelimit_entries" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "hash" {
    null = false
    type = character_varying(128)
  }
  column "delete_after" {
    null = false
    type = timestamp(0)
  }
  primary_key {
    columns = [column.id]
  }
  index "ratelimit_delete_after" {
    columns = [column.delete_after]
  }
  index "ratelimit_hash" {
    columns = [column.hash]
  }
}
table "oc_reactions" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "parent_id" {
    null = false
    type = bigint
  }
  column "message_id" {
    null = false
    type = bigint
  }
  column "actor_type" {
    null    = false
    type    = character_varying(64)
    default = ""
  }
  column "actor_id" {
    null    = false
    type    = character_varying(64)
    default = ""
  }
  column "reaction" {
    null = false
    type = character_varying(32)
  }
  primary_key {
    columns = [column.id]
  }
  index "comment_reaction" {
    columns = [column.reaction]
  }
  index "comment_reaction_parent_id" {
    columns = [column.parent_id]
  }
  index "comment_reaction_unique" {
    unique  = true
    columns = [column.parent_id, column.actor_type, column.actor_id, column.reaction]
  }
}
table "oc_recent_contact" {
  schema = schema.public
  column "id" {
    null = false
    type = serial
  }
  column "actor_uid" {
    null = false
    type = character_varying(64)
  }
  column "uid" {
    null    = true
    type    = character_varying(64)
    default = sql("NULL::character varying")
  }
  column "email" {
    null    = true
    type    = character_varying(255)
    default = sql("NULL::character varying")
  }
  column "federated_cloud_id" {
    null    = true
    type    = character_varying(255)
    default = sql("NULL::character varying")
  }
  column "card" {
    null = false
    type = bytea
  }
  column "last_contact" {
    null = false
    type = integer
  }
  primary_key {
    columns = [column.id]
  }
  index "recent_contact_actor_uid" {
    columns = [column.actor_uid]
  }
  index "recent_contact_email" {
    columns = [column.email]
  }
  index "recent_contact_fed_id" {
    columns = [column.federated_cloud_id]
  }
  index "recent_contact_id_uid" {
    columns = [column.id, column.actor_uid]
  }
  index "recent_contact_last_contact" {
    columns = [column.last_contact]
  }
  index "recent_contact_uid" {
    columns = [column.uid]
  }
}
table "oc_schedulingobjects" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "principaluri" {
    null    = true
    type    = character_varying(255)
    default = sql("NULL::character varying")
  }
  column "calendardata" {
    null = true
    type = bytea
  }
  column "uri" {
    null    = true
    type    = character_varying(255)
    default = sql("NULL::character varying")
  }
  column "lastmodified" {
    null = true
    type = integer
  }
  column "etag" {
    null    = true
    type    = character_varying(32)
    default = sql("NULL::character varying")
  }
  column "size" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  index "schedulobj_lastmodified_idx" {
    columns = [column.lastmodified]
  }
  index "schedulobj_principuri_index" {
    columns = [column.principaluri]
  }
}
table "oc_sec_signatory" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "key_id_sum" {
    null = false
    type = character_varying(127)
  }
  column "key_id" {
    null = false
    type = character_varying(512)
  }
  column "host" {
    null = false
    type = character_varying(512)
  }
  column "provider_id" {
    null = false
    type = character_varying(31)
  }
  column "account" {
    null    = true
    type    = character_varying(127)
    default = ""
  }
  column "public_key" {
    null    = false
    type    = text
    default = ""
  }
  column "metadata" {
    null    = false
    type    = text
    default = "[]"
  }
  column "type" {
    null    = false
    type    = smallint
    default = 9
  }
  column "status" {
    null    = false
    type    = smallint
    default = 0
  }
  column "creation" {
    null    = true
    type    = integer
    default = 0
  }
  column "last_updated" {
    null    = true
    type    = integer
    default = 0
  }
  primary_key {
    columns = [column.id]
  }
  index "sec_sig_key" {
    columns = [column.key_id_sum, column.provider_id]
  }
  index "sec_sig_unic" {
    unique  = true
    columns = [column.provider_id, column.host, column.account]
  }
}
table "oc_share" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "share_type" {
    null    = false
    type    = smallint
    default = 0
  }
  column "share_with" {
    null    = true
    type    = character_varying(255)
    default = sql("NULL::character varying")
  }
  column "password" {
    null    = true
    type    = character_varying(255)
    default = sql("NULL::character varying")
  }
  column "uid_owner" {
    null    = false
    type    = character_varying(64)
    default = ""
  }
  column "uid_initiator" {
    null    = true
    type    = character_varying(64)
    default = sql("NULL::character varying")
  }
  column "parent" {
    null = true
    type = bigint
  }
  column "item_type" {
    null    = false
    type    = character_varying(64)
    default = ""
  }
  column "item_source" {
    null    = true
    type    = character_varying(255)
    default = sql("NULL::character varying")
  }
  column "item_target" {
    null    = true
    type    = character_varying(255)
    default = sql("NULL::character varying")
  }
  column "file_source" {
    null = true
    type = bigint
  }
  column "file_target" {
    null    = true
    type    = character_varying(512)
    default = sql("NULL::character varying")
  }
  column "permissions" {
    null    = false
    type    = smallint
    default = 0
  }
  column "stime" {
    null    = false
    type    = bigint
    default = 0
  }
  column "accepted" {
    null    = false
    type    = smallint
    default = 0
  }
  column "expiration" {
    null    = true
    type    = timestamp(0)
    default = sql("NULL::timestamp without time zone")
  }
  column "token" {
    null    = true
    type    = character_varying(32)
    default = sql("NULL::character varying")
  }
  column "mail_send" {
    null    = false
    type    = smallint
    default = 0
  }
  column "share_name" {
    null    = true
    type    = character_varying(64)
    default = sql("NULL::character varying")
  }
  column "password_by_talk" {
    null    = true
    type    = boolean
    default = false
  }
  column "note" {
    null = true
    type = text
  }
  column "hide_download" {
    null    = true
    type    = smallint
    default = 0
  }
  column "label" {
    null    = true
    type    = character_varying(255)
    default = sql("NULL::character varying")
  }
  column "attributes" {
    null = true
    type = json
  }
  column "password_expiration_time" {
    null    = true
    type    = timestamp(0)
    default = sql("NULL::timestamp without time zone")
  }
  column "reminder_sent" {
    null    = true
    type    = boolean
    default = false
  }
  primary_key {
    columns = [column.id]
  }
  index "file_source_index" {
    columns = [column.file_source]
  }
  index "initiator_index" {
    columns = [column.uid_initiator]
  }
  index "item_share_type_index" {
    columns = [column.item_type, column.share_type]
  }
  index "owner_index" {
    columns = [column.uid_owner]
  }
  index "parent_index" {
    columns = [column.parent]
  }
  index "share_with_file_target_index" {
    columns = [column.share_with, column.file_target]
  }
  index "share_with_index" {
    columns = [column.share_with]
  }
  index "token_index" {
    columns = [column.token]
  }
}
table "oc_share_external" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
  }
  column "parent" {
    null    = true
    type    = bigint
    default = -1
  }
  column "share_type" {
    null = true
    type = integer
  }
  column "remote" {
    null = false
    type = character_varying(512)
  }
  column "remote_id" {
    null    = true
    type    = character_varying(255)
    default = ""
  }
  column "share_token" {
    null = false
    type = character_varying(64)
  }
  column "password" {
    null    = true
    type    = character_varying(64)
    default = sql("NULL::character varying")
  }
  column "name" {
    null = false
    type = character_varying(4000)
  }
  column "owner" {
    null = false
    type = character_varying(255)
  }
  column "user" {
    null = false
    type = character_varying(64)
  }
  column "mountpoint" {
    null = false
    type = character_varying(4000)
  }
  column "mountpoint_hash" {
    null = false
    type = character_varying(32)
  }
  column "accepted" {
    null    = false
    type    = integer
    default = 0
  }
  primary_key {
    columns = [column.id]
  }
  index "sh_external_mp" {
    unique  = true
    columns = [column.user, column.mountpoint_hash]
  }
  index "user_mountpoint_index" {
    columns = [column.user, column.mountpoint]
  }
}
table "oc_shares_limits" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(32)
  }
  column "limit" {
    null = false
    type = bigint
  }
  column "downloads" {
    null    = false
    type    = bigint
    default = 0
  }
  primary_key {
    columns = [column.id]
  }
}
table "oc_storages" {
  schema = schema.public
  column "numeric_id" {
    null = false
    type = bigserial
  }
  column "id" {
    null    = true
    type    = character_varying(64)
    default = sql("NULL::character varying")
  }
  column "available" {
    null    = false
    type    = integer
    default = 1
  }
  column "last_checked" {
    null = true
    type = integer
  }
  primary_key {
    columns = [column.numeric_id]
  }
  index "storages_id_index" {
    unique  = true
    columns = [column.id]
  }
}
table "oc_storages_credentials" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "user" {
    null    = true
    type    = character_varying(64)
    default = sql("NULL::character varying")
  }
  column "identifier" {
    null = false
    type = character_varying(64)
  }
  column "credentials" {
    null = true
    type = text
  }
  primary_key {
    columns = [column.id]
  }
  index "stocred_ui" {
    unique  = true
    columns = [column.user, column.identifier]
  }
  index "stocred_user" {
    columns = [column.user]
  }
}
table "oc_systemtag" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "name" {
    null    = false
    type    = character_varying(64)
    default = ""
  }
  column "visibility" {
    null    = false
    type    = smallint
    default = 1
  }
  column "editable" {
    null    = false
    type    = smallint
    default = 1
  }
  column "etag" {
    null    = true
    type    = character_varying(32)
    default = sql("NULL::character varying")
  }
  column "color" {
    null    = true
    type    = character_varying(6)
    default = sql("NULL::character varying")
  }
  primary_key {
    columns = [column.id]
  }
  index "tag_ident" {
    unique  = true
    columns = [column.name, column.visibility, column.editable]
  }
}
table "oc_systemtag_group" {
  schema = schema.public
  column "systemtagid" {
    null    = false
    type    = bigint
    default = 0
  }
  column "gid" {
    null = false
    type = character_varying(255)
  }
  primary_key {
    columns = [column.gid, column.systemtagid]
  }
}
table "oc_systemtag_object_mapping" {
  schema = schema.public
  column "objectid" {
    null    = false
    type    = character_varying(64)
    default = ""
  }
  column "objecttype" {
    null    = false
    type    = character_varying(64)
    default = ""
  }
  column "systemtagid" {
    null    = false
    type    = bigint
    default = 0
  }
  primary_key {
    columns = [column.objecttype, column.objectid, column.systemtagid]
  }
  index "systag_by_objectid" {
    columns = [column.objectid]
  }
  index "systag_by_tagid" {
    columns = [column.systemtagid, column.objecttype]
  }
  index "systag_objecttype" {
    columns = [column.objecttype]
  }
}
table "oc_taskprocessing_tasks" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "type" {
    null = false
    type = character_varying(255)
  }
  column "input" {
    null = false
    type = text
  }
  column "output" {
    null = true
    type = text
  }
  column "status" {
    null    = true
    type    = integer
    default = 0
  }
  column "user_id" {
    null    = true
    type    = character_varying(64)
    default = sql("NULL::character varying")
  }
  column "app_id" {
    null    = false
    type    = character_varying(32)
    default = ""
  }
  column "custom_id" {
    null    = true
    type    = character_varying(255)
    default = ""
  }
  column "last_updated" {
    null    = true
    type    = integer
    default = 0
  }
  column "completion_expected_at" {
    null    = true
    type    = timestamp(0)
    default = sql("NULL::timestamp without time zone")
  }
  column "progress" {
    null    = true
    type    = double_precision
    default = 0
  }
  column "error_message" {
    null    = true
    type    = character_varying(4000)
    default = sql("NULL::character varying")
  }
  column "scheduled_at" {
    null = true
    type = integer
  }
  column "started_at" {
    null = true
    type = integer
  }
  column "ended_at" {
    null = true
    type = integer
  }
  column "webhook_uri" {
    null    = true
    type    = character_varying(4000)
    default = sql("NULL::character varying")
  }
  column "webhook_method" {
    null    = true
    type    = character_varying(64)
    default = sql("NULL::character varying")
  }
  column "allow_cleanup" {
    null    = false
    type    = smallint
    default = 1
  }
  column "user_facing_error_message" {
    null    = true
    type    = character_varying(4000)
    default = sql("NULL::character varying")
  }
  column "include_watermark" {
    null    = false
    type    = smallint
    default = 1
  }
  primary_key {
    columns = [column.id]
  }
  index "taskp_tasks_status_type" {
    columns = [column.status, column.type]
  }
  index "taskp_tasks_uid_appid_cid" {
    columns = [column.user_id, column.app_id, column.custom_id]
  }
  index "taskp_tasks_updated" {
    columns = [column.last_updated]
  }
}
table "oc_text2image_tasks" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "input" {
    null = false
    type = text
  }
  column "status" {
    null    = true
    type    = integer
    default = 0
  }
  column "number_of_images" {
    null    = false
    type    = integer
    default = 1
  }
  column "user_id" {
    null    = true
    type    = character_varying(64)
    default = sql("NULL::character varying")
  }
  column "app_id" {
    null    = false
    type    = character_varying(32)
    default = ""
  }
  column "identifier" {
    null    = true
    type    = character_varying(255)
    default = ""
  }
  column "last_updated" {
    null    = true
    type    = timestamp(0)
    default = sql("NULL::timestamp without time zone")
  }
  column "completion_expected_at" {
    null    = true
    type    = timestamp(0)
    default = sql("NULL::timestamp without time zone")
  }
  primary_key {
    columns = [column.id]
  }
  index "t2i_tasks_status" {
    columns = [column.status]
  }
  index "t2i_tasks_uid_appid_ident" {
    columns = [column.user_id, column.app_id, column.identifier]
  }
  index "t2i_tasks_updated" {
    columns = [column.last_updated]
  }
}
table "oc_text_documents" {
  schema = schema.public
  column "id" {
    null = false
    type = bigint
  }
  column "current_version" {
    null    = true
    type    = bigint
    default = 0
  }
  column "last_saved_version" {
    null    = true
    type    = bigint
    default = 0
  }
  column "last_saved_version_time" {
    null = false
    type = bigint
  }
  column "last_saved_version_etag" {
    null    = true
    type    = character_varying(64)
    default = ""
  }
  column "base_version_etag" {
    null    = true
    type    = character_varying(64)
    default = ""
  }
  column "checksum" {
    null    = true
    type    = character_varying(8)
    default = sql("NULL::character varying")
  }
  primary_key {
    columns = [column.id]
  }
}
table "oc_text_sessions" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "user_id" {
    null    = true
    type    = character_varying(64)
    default = sql("NULL::character varying")
  }
  column "guest_name" {
    null    = true
    type    = character_varying(64)
    default = sql("NULL::character varying")
  }
  column "color" {
    null    = true
    type    = character_varying(7)
    default = sql("NULL::character varying")
  }
  column "token" {
    null = false
    type = character_varying(64)
  }
  column "document_id" {
    null = false
    type = bigint
  }
  column "last_contact" {
    null = false
    type = bigint
  }
  column "last_awareness_message" {
    null    = true
    type    = text
    default = ""
  }
  primary_key {
    columns = [column.id]
  }
  index "rd_session_token_idx" {
    columns = [column.token]
  }
  index "ts_docid_lastcontact" {
    columns = [column.document_id, column.last_contact]
  }
  index "ts_lastcontact" {
    columns = [column.last_contact]
  }
}
table "oc_text_steps" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "document_id" {
    null = false
    type = bigint
  }
  column "session_id" {
    null = false
    type = bigint
  }
  column "data" {
    null = false
    type = text
  }
  column "version" {
    null    = true
    type    = bigint
    default = 0
  }
  column "timestamp" {
    null    = false
    type    = bigint
    default = 0
  }
  primary_key {
    columns = [column.id]
  }
  index "rd_steps_did_idx" {
    columns = [column.document_id]
  }
  index "rd_steps_version_idx" {
    columns = [column.version]
  }
  index "textstep_session" {
    columns = [column.session_id]
  }
}
table "oc_textprocessing_tasks" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "type" {
    null = false
    type = character_varying(255)
  }
  column "input" {
    null = false
    type = text
  }
  column "output" {
    null = true
    type = text
  }
  column "status" {
    null    = true
    type    = integer
    default = 0
  }
  column "user_id" {
    null    = true
    type    = character_varying(64)
    default = sql("NULL::character varying")
  }
  column "app_id" {
    null    = false
    type    = character_varying(32)
    default = ""
  }
  column "identifier" {
    null    = false
    type    = character_varying(255)
    default = ""
  }
  column "last_updated" {
    null    = true
    type    = integer
    default = 0
  }
  column "completion_expected_at" {
    null    = true
    type    = timestamp(0)
    default = sql("NULL::timestamp without time zone")
  }
  primary_key {
    columns = [column.id]
  }
  index "tp_tasks_status_type_nonunique" {
    columns = [column.status, column.type]
  }
  index "tp_tasks_uid_appid_ident" {
    columns = [column.user_id, column.app_id, column.identifier]
  }
  index "tp_tasks_updated" {
    columns = [column.last_updated]
  }
}
table "oc_trusted_servers" {
  schema = schema.public
  column "id" {
    null = false
    type = serial
  }
  column "url" {
    null = false
    type = character_varying(512)
  }
  column "url_hash" {
    null    = false
    type    = character_varying(255)
    default = ""
  }
  column "token" {
    null    = true
    type    = character_varying(128)
    default = sql("NULL::character varying")
  }
  column "shared_secret" {
    null    = true
    type    = character_varying(256)
    default = sql("NULL::character varying")
  }
  column "status" {
    null    = false
    type    = integer
    default = 2
  }
  column "sync_token" {
    null    = true
    type    = character_varying(512)
    default = sql("NULL::character varying")
  }
  primary_key {
    columns = [column.id]
  }
  index "url_hash" {
    unique  = true
    columns = [column.url_hash]
  }
}
table "oc_twofactor_backupcodes" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "user_id" {
    null    = false
    type    = character_varying(64)
    default = ""
  }
  column "code" {
    null = false
    type = character_varying(128)
  }
  column "used" {
    null    = false
    type    = smallint
    default = 0
  }
  primary_key {
    columns = [column.id]
  }
  index "twofactor_backupcodes_uid" {
    columns = [column.user_id]
  }
}
table "oc_twofactor_providers" {
  schema = schema.public
  column "provider_id" {
    null = false
    type = character_varying(32)
  }
  column "uid" {
    null = false
    type = character_varying(64)
  }
  column "enabled" {
    null = false
    type = smallint
  }
  primary_key {
    columns = [column.provider_id, column.uid]
  }
  index "twofactor_providers_uid" {
    columns = [column.uid]
  }
}
table "oc_twofactor_totp_secrets" {
  schema = schema.public
  column "id" {
    null = false
    type = serial
  }
  column "user_id" {
    null    = false
    type    = character_varying(64)
    default = ""
  }
  column "secret" {
    null = false
    type = text
  }
  column "state" {
    null    = false
    type    = integer
    default = 2
  }
  column "last_counter" {
    null    = false
    type    = bigint
    default = -1
  }
  primary_key {
    columns = [column.id]
  }
  index "totp_secrets_user_id" {
    unique  = true
    columns = [column.user_id]
  }
}
table "oc_user_status" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "user_id" {
    null = false
    type = character_varying(255)
  }
  column "status" {
    null = false
    type = character_varying(255)
  }
  column "status_timestamp" {
    null = false
    type = integer
  }
  column "is_user_defined" {
    null = true
    type = boolean
  }
  column "message_id" {
    null    = true
    type    = character_varying(255)
    default = sql("NULL::character varying")
  }
  column "custom_icon" {
    null    = true
    type    = character_varying(255)
    default = sql("NULL::character varying")
  }
  column "custom_message" {
    null = true
    type = text
  }
  column "clear_at" {
    null = true
    type = integer
  }
  column "is_backup" {
    null    = true
    type    = boolean
    default = false
  }
  column "status_message_timestamp" {
    null    = false
    type    = integer
    default = 0
  }
  primary_key {
    columns = [column.id]
  }
  index "user_status_clr_ix" {
    columns = [column.clear_at]
  }
  index "user_status_iud_ix" {
    columns = [column.is_user_defined, column.status]
  }
  index "user_status_mtstmp_ix" {
    columns = [column.status_message_timestamp]
  }
  index "user_status_tstmp_ix" {
    columns = [column.status_timestamp]
  }
  index "user_status_uid_ix" {
    unique  = true
    columns = [column.user_id]
  }
}
table "oc_user_transfer_owner" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "source_user" {
    null = false
    type = character_varying(64)
  }
  column "target_user" {
    null = false
    type = character_varying(64)
  }
  column "file_id" {
    null = false
    type = bigint
  }
  column "node_name" {
    null = false
    type = character_varying(255)
  }
  primary_key {
    columns = [column.id]
  }
}
table "oc_users" {
  schema = schema.public
  column "uid" {
    null    = false
    type    = character_varying(64)
    default = ""
  }
  column "displayname" {
    null    = true
    type    = character_varying(64)
    default = sql("NULL::character varying")
  }
  column "password" {
    null    = false
    type    = character_varying(255)
    default = ""
  }
  column "uid_lower" {
    null    = true
    type    = character_varying(64)
    default = ""
  }
  primary_key {
    columns = [column.uid]
  }
  index "user_uid_lower" {
    columns = [column.uid_lower]
  }
}
table "oc_vcategory" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "uid" {
    null    = false
    type    = character_varying(64)
    default = ""
  }
  column "type" {
    null    = false
    type    = character_varying(64)
    default = ""
  }
  column "category" {
    null    = false
    type    = character_varying(255)
    default = ""
  }
  primary_key {
    columns = [column.id]
  }
  index "category_index" {
    columns = [column.category]
  }
  index "type_index" {
    columns = [column.type]
  }
  index "uid_index" {
    columns = [column.uid]
  }
  index "unique_category_per_user" {
    unique  = true
    columns = [column.uid, column.type, column.category]
  }
}
table "oc_vcategory_to_object" {
  schema = schema.public
  column "objid" {
    null    = false
    type    = bigint
    default = 0
  }
  column "categoryid" {
    null    = false
    type    = bigint
    default = 0
  }
  column "type" {
    null    = false
    type    = character_varying(64)
    default = ""
  }
  primary_key {
    columns = [column.categoryid, column.objid, column.type]
  }
  index "vcategory_objectd_index" {
    columns = [column.objid, column.type]
  }
}
table "oc_webauthn" {
  schema = schema.public
  column "id" {
    null = false
    type = serial
  }
  column "uid" {
    null = false
    type = character_varying(64)
  }
  column "name" {
    null = false
    type = character_varying(64)
  }
  column "public_key_credential_id" {
    null = false
    type = character_varying(512)
  }
  column "data" {
    null = false
    type = text
  }
  column "user_verification" {
    null    = true
    type    = boolean
    default = false
  }
  primary_key {
    columns = [column.id]
  }
  index "webauthn_publickeycredentialid" {
    columns = [column.public_key_credential_id]
  }
  index "webauthn_uid" {
    columns = [column.uid]
  }
}
table "oc_webhook_listeners" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "app_id" {
    null    = true
    type    = character_varying(64)
    default = sql("NULL::character varying")
  }
  column "user_id" {
    null    = true
    type    = character_varying(64)
    default = sql("NULL::character varying")
  }
  column "http_method" {
    null = false
    type = character_varying(32)
  }
  column "uri" {
    null = false
    type = character_varying(4000)
  }
  column "event" {
    null = false
    type = character_varying(4000)
  }
  column "event_filter" {
    null = true
    type = text
  }
  column "user_id_filter" {
    null    = true
    type    = character_varying(64)
    default = sql("NULL::character varying")
  }
  column "headers" {
    null = true
    type = text
  }
  column "auth_method" {
    null    = false
    type    = character_varying(16)
    default = ""
  }
  column "auth_data" {
    null = true
    type = text
  }
  column "token_needed" {
    null = true
    type = text
  }
  primary_key {
    columns = [column.id]
  }
}
table "oc_webhook_tokens" {
  schema = schema.public
  column "id" {
    null = false
    type = bigserial
  }
  column "token_id" {
    null = false
    type = bigint
  }
  column "user_id" {
    null    = true
    type    = character_varying(64)
    default = sql("NULL::character varying")
  }
  column "created_at" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
}
schema "public" {
  comment = "standard public schema"
}
