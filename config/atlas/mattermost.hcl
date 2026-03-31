Notice: This Atlas edition lacks support for features such as checkpoints,
testing, down migrations, and more. Additionally, advanced database objects such as views,
triggers, and stored procedures are not supported. To read more: https://atlasgo.io/community-edition

To install the non-community version of Atlas, use the following command:

	curl -sSf https://atlasgo.sh | sh

Or, visit the website to see all installation options:

	https://atlasgo.io/docs#installation

table "accesscontrolpolicies" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(26)
  }
  column "name" {
    null = false
    type = character_varying(128)
  }
  column "type" {
    null = false
    type = character_varying(128)
  }
  column "active" {
    null = false
    type = boolean
  }
  column "createat" {
    null = false
    type = bigint
  }
  column "revision" {
    null = false
    type = integer
  }
  column "version" {
    null = false
    type = character_varying(8)
  }
  column "data" {
    null = true
    type = jsonb
  }
  column "props" {
    null = true
    type = jsonb
  }
  primary_key {
    columns = [column.id]
  }
}
table "accesscontrolpolicyhistory" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(26)
  }
  column "name" {
    null = false
    type = character_varying(128)
  }
  column "type" {
    null = false
    type = character_varying(128)
  }
  column "createat" {
    null = false
    type = bigint
  }
  column "revision" {
    null = false
    type = integer
  }
  column "version" {
    null = false
    type = character_varying(8)
  }
  column "data" {
    null = true
    type = jsonb
  }
  column "props" {
    null = true
    type = jsonb
  }
  primary_key {
    columns = [column.id, column.revision]
  }
}
table "audits" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(26)
  }
  column "createat" {
    null = true
    type = bigint
  }
  column "userid" {
    null = true
    type = character_varying(26)
  }
  column "action" {
    null = true
    type = character_varying(512)
  }
  column "extrainfo" {
    null = true
    type = character_varying(1024)
  }
  column "ipaddress" {
    null = true
    type = character_varying(64)
  }
  column "sessionid" {
    null = true
    type = character_varying(26)
  }
  primary_key {
    columns = [column.id]
  }
  index "idx_audits_user_id" {
    columns = [column.userid]
  }
}
table "bots" {
  schema = schema.public
  column "userid" {
    null = false
    type = character_varying(26)
  }
  column "description" {
    null = true
    type = character_varying(1024)
  }
  column "ownerid" {
    null = true
    type = character_varying(190)
  }
  column "createat" {
    null = true
    type = bigint
  }
  column "updateat" {
    null = true
    type = bigint
  }
  column "deleteat" {
    null = true
    type = bigint
  }
  column "lasticonupdate" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.userid]
  }
}
table "calls" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(26)
  }
  column "channelid" {
    null = true
    type = character_varying(26)
  }
  column "startat" {
    null = true
    type = bigint
  }
  column "endat" {
    null = true
    type = bigint
  }
  column "createat" {
    null = true
    type = bigint
  }
  column "deleteat" {
    null = true
    type = bigint
  }
  column "title" {
    null = true
    type = character_varying(256)
  }
  column "postid" {
    null = true
    type = character_varying(26)
  }
  column "threadid" {
    null = true
    type = character_varying(26)
  }
  column "ownerid" {
    null = true
    type = character_varying(26)
  }
  column "participants" {
    null = false
    type = jsonb
  }
  column "stats" {
    null = false
    type = jsonb
  }
  column "props" {
    null = false
    type = jsonb
  }
  primary_key {
    columns = [column.id]
  }
  index "idx_calls_channel_id" {
    columns = [column.channelid]
  }
  index "idx_calls_end_at" {
    columns = [column.endat]
  }
}
table "calls_channels" {
  schema = schema.public
  column "channelid" {
    null = false
    type = character_varying(26)
  }
  column "enabled" {
    null = true
    type = boolean
  }
  column "props" {
    null = false
    type = jsonb
  }
  primary_key {
    columns = [column.channelid]
  }
}
table "calls_jobs" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(26)
  }
  column "callid" {
    null = true
    type = character_varying(26)
  }
  column "type" {
    null = true
    type = character_varying(64)
  }
  column "creatorid" {
    null = true
    type = character_varying(26)
  }
  column "initat" {
    null = true
    type = bigint
  }
  column "startat" {
    null = true
    type = bigint
  }
  column "endat" {
    null = true
    type = bigint
  }
  column "props" {
    null = false
    type = jsonb
  }
  primary_key {
    columns = [column.id]
  }
  index "idx_calls_jobs_call_id" {
    columns = [column.callid]
  }
}
table "calls_sessions" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(26)
  }
  column "callid" {
    null = true
    type = character_varying(26)
  }
  column "userid" {
    null = true
    type = character_varying(26)
  }
  column "joinat" {
    null = true
    type = bigint
  }
  column "unmuted" {
    null = true
    type = boolean
  }
  column "raisedhand" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  index "idx_calls_sessions_call_id" {
    columns = [column.callid]
  }
}
table "channelbookmarks" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(26)
  }
  column "ownerid" {
    null = false
    type = character_varying(26)
  }
  column "channelid" {
    null = false
    type = character_varying(26)
  }
  column "fileinfoid" {
    null    = true
    type    = character_varying(26)
    default = sql("NULL::character varying")
  }
  column "createat" {
    null    = true
    type    = bigint
    default = 0
  }
  column "updateat" {
    null    = true
    type    = bigint
    default = 0
  }
  column "deleteat" {
    null    = true
    type    = bigint
    default = 0
  }
  column "displayname" {
    null    = true
    type    = text
    default = ""
  }
  column "sortorder" {
    null    = true
    type    = integer
    default = 0
  }
  column "linkurl" {
    null = true
    type = text
  }
  column "imageurl" {
    null = true
    type = text
  }
  column "emoji" {
    null    = true
    type    = character_varying(64)
    default = sql("NULL::character varying")
  }
  column "type" {
    null    = true
    type    = enum.channel_bookmark_type
    default = "link"
  }
  column "originalid" {
    null    = true
    type    = character_varying(26)
    default = sql("NULL::character varying")
  }
  column "parentid" {
    null    = true
    type    = character_varying(26)
    default = sql("NULL::character varying")
  }
  primary_key {
    columns = [column.id]
  }
  index "idx_channelbookmarks_channelid" {
    columns = [column.channelid]
  }
  index "idx_channelbookmarks_delete_at" {
    columns = [column.deleteat]
  }
  index "idx_channelbookmarks_update_at" {
    columns = [column.updateat]
  }
}
table "channelmemberhistory" {
  schema = schema.public
  column "channelid" {
    null = false
    type = character_varying(26)
  }
  column "userid" {
    null = false
    type = character_varying(26)
  }
  column "jointime" {
    null = false
    type = bigint
  }
  column "leavetime" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.channelid, column.userid, column.jointime]
  }
}
table "channelmembers" {
  schema = schema.public
  column "channelid" {
    null = false
    type = character_varying(26)
  }
  column "userid" {
    null = false
    type = character_varying(26)
  }
  column "roles" {
    null = true
    type = character_varying(256)
  }
  column "lastviewedat" {
    null = true
    type = bigint
  }
  column "msgcount" {
    null = true
    type = bigint
  }
  column "mentioncount" {
    null = true
    type = bigint
  }
  column "notifyprops" {
    null = true
    type = jsonb
  }
  column "lastupdateat" {
    null = true
    type = bigint
  }
  column "schemeuser" {
    null = true
    type = boolean
  }
  column "schemeadmin" {
    null = true
    type = boolean
  }
  column "schemeguest" {
    null = true
    type = boolean
  }
  column "mentioncountroot" {
    null = true
    type = bigint
  }
  column "msgcountroot" {
    null = true
    type = bigint
  }
  column "urgentmentioncount" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.channelid, column.userid]
  }
  index "idx_channelmembers_channel_id_scheme_guest_user_id" {
    columns = [column.channelid, column.schemeguest, column.userid]
  }
  index "idx_channelmembers_user_id_channel_id_last_viewed_at" {
    columns = [column.userid, column.channelid, column.lastviewedat]
  }
}
table "channels" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(26)
  }
  column "createat" {
    null = true
    type = bigint
  }
  column "updateat" {
    null = true
    type = bigint
  }
  column "deleteat" {
    null = true
    type = bigint
  }
  column "teamid" {
    null = true
    type = character_varying(26)
  }
  column "type" {
    null = true
    type = enum.channel_type
  }
  column "displayname" {
    null = true
    type = character_varying(64)
  }
  column "name" {
    null = true
    type = character_varying(64)
  }
  column "header" {
    null = true
    type = character_varying(1024)
  }
  column "purpose" {
    null = true
    type = character_varying(250)
  }
  column "lastpostat" {
    null = true
    type = bigint
  }
  column "totalmsgcount" {
    null = true
    type = bigint
  }
  column "extraupdateat" {
    null = true
    type = bigint
  }
  column "creatorid" {
    null = true
    type = character_varying(26)
  }
  column "schemeid" {
    null = true
    type = character_varying(26)
  }
  column "groupconstrained" {
    null = true
    type = boolean
  }
  column "shared" {
    null = true
    type = boolean
  }
  column "totalmsgcountroot" {
    null = true
    type = bigint
  }
  column "lastrootpostat" {
    null    = true
    type    = bigint
    default = 0
  }
  column "bannerinfo" {
    null = true
    type = jsonb
  }
  column "defaultcategoryname" {
    null    = false
    type    = character_varying(64)
    default = ""
  }
  primary_key {
    columns = [column.id]
  }
  index "idx_channel_search_txt" {
    type = GIN
    on {
      expr = "to_tsvector('english'::regconfig, (((((name)::text || ' '::text) || (displayname)::text) || ' '::text) || (purpose)::text))"
    }
  }
  index "idx_channels_create_at" {
    columns = [column.createat]
  }
  index "idx_channels_delete_at" {
    columns = [column.deleteat]
  }
  index "idx_channels_displayname_lower" {
    on {
      expr = "lower((displayname)::text)"
    }
  }
  index "idx_channels_name_lower" {
    on {
      expr = "lower((name)::text)"
    }
  }
  index "idx_channels_scheme_id" {
    columns = [column.schemeid]
  }
  index "idx_channels_team_id_display_name" {
    columns = [column.teamid, column.displayname]
  }
  index "idx_channels_team_id_type" {
    columns = [column.teamid, column.type]
  }
  index "idx_channels_update_at" {
    columns = [column.updateat]
  }
  unique "channels_name_teamid_key" {
    columns = [column.name, column.teamid]
  }
}
table "clusterdiscovery" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(26)
  }
  column "type" {
    null = true
    type = character_varying(64)
  }
  column "clustername" {
    null = true
    type = character_varying(64)
  }
  column "hostname" {
    null = true
    type = character_varying(512)
  }
  column "gossipport" {
    null = true
    type = integer
  }
  column "port" {
    null = true
    type = integer
  }
  column "createat" {
    null = true
    type = bigint
  }
  column "lastpingat" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
}
table "commands" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(26)
  }
  column "token" {
    null = true
    type = character_varying(26)
  }
  column "createat" {
    null = true
    type = bigint
  }
  column "updateat" {
    null = true
    type = bigint
  }
  column "deleteat" {
    null = true
    type = bigint
  }
  column "creatorid" {
    null = true
    type = character_varying(26)
  }
  column "teamid" {
    null = true
    type = character_varying(26)
  }
  column "trigger" {
    null = true
    type = character_varying(128)
  }
  column "method" {
    null = true
    type = character_varying(1)
  }
  column "username" {
    null = true
    type = character_varying(64)
  }
  column "iconurl" {
    null = true
    type = character_varying(1024)
  }
  column "autocomplete" {
    null = true
    type = boolean
  }
  column "autocompletedesc" {
    null = true
    type = character_varying(1024)
  }
  column "autocompletehint" {
    null = true
    type = character_varying(1024)
  }
  column "displayname" {
    null = true
    type = character_varying(64)
  }
  column "description" {
    null = true
    type = character_varying(128)
  }
  column "url" {
    null = true
    type = character_varying(1024)
  }
  column "pluginid" {
    null = true
    type = character_varying(190)
  }
  primary_key {
    columns = [column.id]
  }
  index "idx_command_create_at" {
    columns = [column.createat]
  }
  index "idx_command_delete_at" {
    columns = [column.deleteat]
  }
  index "idx_command_team_id" {
    columns = [column.teamid]
  }
  index "idx_command_update_at" {
    columns = [column.updateat]
  }
}
table "commandwebhooks" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(26)
  }
  column "createat" {
    null = true
    type = bigint
  }
  column "commandid" {
    null = true
    type = character_varying(26)
  }
  column "userid" {
    null = true
    type = character_varying(26)
  }
  column "channelid" {
    null = true
    type = character_varying(26)
  }
  column "rootid" {
    null = true
    type = character_varying(26)
  }
  column "usecount" {
    null = true
    type = integer
  }
  primary_key {
    columns = [column.id]
  }
  index "idx_command_webhook_create_at" {
    columns = [column.createat]
  }
}
table "compliances" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(26)
  }
  column "createat" {
    null = true
    type = bigint
  }
  column "userid" {
    null = true
    type = character_varying(26)
  }
  column "status" {
    null = true
    type = character_varying(64)
  }
  column "count" {
    null = true
    type = integer
  }
  column "desc" {
    null = true
    type = character_varying(512)
  }
  column "type" {
    null = true
    type = character_varying(64)
  }
  column "startat" {
    null = true
    type = bigint
  }
  column "endat" {
    null = true
    type = bigint
  }
  column "keywords" {
    null = true
    type = character_varying(512)
  }
  column "emails" {
    null = true
    type = character_varying(1024)
  }
  primary_key {
    columns = [column.id]
  }
}
table "db_lock" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(64)
  }
  column "expireat" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
}
table "db_migrations" {
  schema = schema.public
  column "version" {
    null = false
    type = bigint
  }
  column "name" {
    null = false
    type = character_varying
  }
  primary_key {
    columns = [column.version]
  }
}
table "db_migrations_calls" {
  schema = schema.public
  column "version" {
    null = false
    type = bigint
  }
  column "name" {
    null = false
    type = character_varying
  }
  primary_key {
    columns = [column.version]
  }
}
table "desktoptokens" {
  schema = schema.public
  column "token" {
    null = false
    type = character_varying(64)
  }
  column "createat" {
    null = false
    type = bigint
  }
  column "userid" {
    null = false
    type = character_varying(26)
  }
  primary_key {
    columns = [column.token]
  }
  index "idx_desktoptokens_token_createat" {
    columns = [column.token, column.createat]
  }
}
table "drafts" {
  schema = schema.public
  column "createat" {
    null = true
    type = bigint
  }
  column "updateat" {
    null = true
    type = bigint
  }
  column "deleteat" {
    null = true
    type = bigint
  }
  column "userid" {
    null = false
    type = character_varying(26)
  }
  column "channelid" {
    null = false
    type = character_varying(26)
  }
  column "rootid" {
    null    = false
    type    = character_varying(26)
    default = ""
  }
  column "message" {
    null = true
    type = character_varying(65535)
  }
  column "props" {
    null = true
    type = character_varying(8000)
  }
  column "fileids" {
    null = true
    type = character_varying(300)
  }
  column "priority" {
    null = true
    type = text
  }
  primary_key {
    columns = [column.userid, column.channelid, column.rootid]
  }
}
table "emoji" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(26)
  }
  column "createat" {
    null = true
    type = bigint
  }
  column "updateat" {
    null = true
    type = bigint
  }
  column "deleteat" {
    null = true
    type = bigint
  }
  column "creatorid" {
    null = true
    type = character_varying(26)
  }
  column "name" {
    null = true
    type = character_varying(64)
  }
  primary_key {
    columns = [column.id]
  }
  index "idx_emoji_create_at" {
    columns = [column.createat]
  }
  index "idx_emoji_delete_at" {
    columns = [column.deleteat]
  }
  index "idx_emoji_update_at" {
    columns = [column.updateat]
  }
  unique "emoji_name_deleteat_key" {
    columns = [column.name, column.deleteat]
  }
}
table "fileinfo" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(26)
  }
  column "creatorid" {
    null = true
    type = character_varying(26)
  }
  column "postid" {
    null = true
    type = character_varying(26)
  }
  column "createat" {
    null = true
    type = bigint
  }
  column "updateat" {
    null = true
    type = bigint
  }
  column "deleteat" {
    null = true
    type = bigint
  }
  column "path" {
    null = true
    type = character_varying(512)
  }
  column "thumbnailpath" {
    null = true
    type = character_varying(512)
  }
  column "previewpath" {
    null = true
    type = character_varying(512)
  }
  column "name" {
    null = true
    type = character_varying(256)
  }
  column "extension" {
    null = true
    type = character_varying(64)
  }
  column "size" {
    null = true
    type = bigint
  }
  column "mimetype" {
    null = true
    type = character_varying(256)
  }
  column "width" {
    null = true
    type = integer
  }
  column "height" {
    null = true
    type = integer
  }
  column "haspreviewimage" {
    null = true
    type = boolean
  }
  column "minipreview" {
    null = true
    type = bytea
  }
  column "content" {
    null = true
    type = text
  }
  column "remoteid" {
    null = true
    type = character_varying(26)
  }
  column "archived" {
    null    = false
    type    = boolean
    default = false
  }
  column "channelid" {
    null = true
    type = character_varying(26)
  }
  primary_key {
    columns = [column.id]
  }
  index "idx_fileinfo_channel_id_create_at" {
    columns = [column.channelid, column.createat]
  }
  index "idx_fileinfo_content_txt" {
    type = GIN
    on {
      expr = "to_tsvector('english'::regconfig, content)"
    }
  }
  index "idx_fileinfo_create_at" {
    columns = [column.createat]
  }
  index "idx_fileinfo_delete_at" {
    columns = [column.deleteat]
  }
  index "idx_fileinfo_extension_at" {
    columns = [column.extension]
  }
  index "idx_fileinfo_name_splitted" {
    type = GIN
    on {
      expr = "to_tsvector('english'::regconfig, translate((name)::text, '.,-'::text, '   '::text))"
    }
  }
  index "idx_fileinfo_name_txt" {
    type = GIN
    on {
      expr = "to_tsvector('english'::regconfig, (name)::text)"
    }
  }
  index "idx_fileinfo_postid_at" {
    columns = [column.postid]
  }
  index "idx_fileinfo_update_at" {
    columns = [column.updateat]
  }
}
table "groupchannels" {
  schema = schema.public
  column "groupid" {
    null = false
    type = character_varying(26)
  }
  column "autoadd" {
    null = true
    type = boolean
  }
  column "schemeadmin" {
    null = true
    type = boolean
  }
  column "createat" {
    null = true
    type = bigint
  }
  column "deleteat" {
    null = true
    type = bigint
  }
  column "updateat" {
    null = true
    type = bigint
  }
  column "channelid" {
    null = false
    type = character_varying(26)
  }
  primary_key {
    columns = [column.groupid, column.channelid]
  }
  index "idx_groupchannels_channelid" {
    columns = [column.channelid]
  }
  index "idx_groupchannels_schemeadmin" {
    columns = [column.schemeadmin]
  }
}
table "groupmembers" {
  schema = schema.public
  column "groupid" {
    null = false
    type = character_varying(26)
  }
  column "userid" {
    null = false
    type = character_varying(26)
  }
  column "createat" {
    null = true
    type = bigint
  }
  column "deleteat" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.groupid, column.userid]
  }
  index "idx_groupmembers_create_at" {
    columns = [column.createat]
  }
}
table "groupteams" {
  schema = schema.public
  column "groupid" {
    null = false
    type = character_varying(26)
  }
  column "autoadd" {
    null = true
    type = boolean
  }
  column "schemeadmin" {
    null = true
    type = boolean
  }
  column "createat" {
    null = true
    type = bigint
  }
  column "deleteat" {
    null = true
    type = bigint
  }
  column "updateat" {
    null = true
    type = bigint
  }
  column "teamid" {
    null = false
    type = character_varying(26)
  }
  primary_key {
    columns = [column.groupid, column.teamid]
  }
  index "idx_groupteams_schemeadmin" {
    columns = [column.schemeadmin]
  }
  index "idx_groupteams_teamid" {
    columns = [column.teamid]
  }
}
table "incomingwebhooks" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(26)
  }
  column "createat" {
    null = true
    type = bigint
  }
  column "updateat" {
    null = true
    type = bigint
  }
  column "deleteat" {
    null = true
    type = bigint
  }
  column "userid" {
    null = true
    type = character_varying(26)
  }
  column "channelid" {
    null = true
    type = character_varying(26)
  }
  column "teamid" {
    null = true
    type = character_varying(26)
  }
  column "displayname" {
    null = true
    type = character_varying(64)
  }
  column "description" {
    null = true
    type = character_varying(500)
  }
  column "username" {
    null = true
    type = character_varying(255)
  }
  column "iconurl" {
    null = true
    type = character_varying(1024)
  }
  column "channellocked" {
    null = true
    type = boolean
  }
  primary_key {
    columns = [column.id]
  }
  index "idx_incoming_webhook_create_at" {
    columns = [column.createat]
  }
  index "idx_incoming_webhook_delete_at" {
    columns = [column.deleteat]
  }
  index "idx_incoming_webhook_team_id" {
    columns = [column.teamid]
  }
  index "idx_incoming_webhook_update_at" {
    columns = [column.updateat]
  }
  index "idx_incoming_webhook_user_id" {
    columns = [column.userid]
  }
}
table "ir_category" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(26)
  }
  column "name" {
    null = false
    type = character_varying(512)
  }
  column "teamid" {
    null = false
    type = character_varying(26)
  }
  column "userid" {
    null = false
    type = character_varying(26)
  }
  column "collapsed" {
    null    = true
    type    = boolean
    default = false
  }
  column "createat" {
    null = false
    type = bigint
  }
  column "updateat" {
    null    = false
    type    = bigint
    default = 0
  }
  column "deleteat" {
    null    = false
    type    = bigint
    default = 0
  }
  primary_key {
    columns = [column.id]
  }
  index "ir_category_teamid_userid" {
    columns = [column.teamid, column.userid]
  }
}
table "ir_category_item" {
  schema = schema.public
  column "type" {
    null = false
    type = character_varying(1)
  }
  column "categoryid" {
    null = false
    type = character_varying(26)
  }
  column "itemid" {
    null = false
    type = character_varying(26)
  }
  primary_key {
    columns = [column.categoryid, column.itemid, column.type]
  }
  foreign_key "ir_category_item_categoryid_fkey" {
    columns     = [column.categoryid]
    ref_columns = [table.ir_category.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "ir_category_item_categoryid" {
    columns = [column.categoryid]
  }
}
table "ir_channelaction" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(26)
  }
  column "channelid" {
    null = true
    type = character_varying(26)
  }
  column "enabled" {
    null    = true
    type    = boolean
    default = false
  }
  column "deleteat" {
    null    = false
    type    = bigint
    default = 0
  }
  column "actiontype" {
    null = false
    type = character_varying(65535)
  }
  column "triggertype" {
    null = false
    type = character_varying(65535)
  }
  column "payload" {
    null = false
    type = json
  }
  primary_key {
    columns = [column.id]
  }
  index "ir_channelaction_channelid" {
    columns = [column.channelid]
  }
}
table "ir_incident" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(26)
  }
  column "name" {
    null = false
    type = character_varying(1024)
  }
  column "description" {
    null = false
    type = character_varying(4096)
  }
  column "isactive" {
    null = false
    type = boolean
  }
  column "commanderuserid" {
    null = false
    type = character_varying(26)
  }
  column "teamid" {
    null = false
    type = character_varying(26)
  }
  column "channelid" {
    null = false
    type = character_varying(26)
  }
  column "createat" {
    null = false
    type = bigint
  }
  column "endat" {
    null    = false
    type    = bigint
    default = 0
  }
  column "deleteat" {
    null    = false
    type    = bigint
    default = 0
  }
  column "activestage" {
    null = false
    type = bigint
  }
  column "postid" {
    null    = false
    type    = character_varying(26)
    default = ""
  }
  column "playbookid" {
    null    = false
    type    = character_varying(26)
    default = ""
  }
  column "checklistsjson" {
    null = false
    type = json
  }
  column "activestagetitle" {
    null    = true
    type    = character_varying(1024)
    default = ""
  }
  column "reminderpostid" {
    null = true
    type = character_varying(26)
  }
  column "broadcastchannelid" {
    null    = true
    type    = character_varying(26)
    default = ""
  }
  column "previousreminder" {
    null    = false
    type    = bigint
    default = 0
  }
  column "remindermessagetemplate" {
    null    = true
    type    = character_varying(65535)
    default = ""
  }
  column "currentstatus" {
    null    = false
    type    = character_varying(1024)
    default = "Active"
  }
  column "reporteruserid" {
    null    = false
    type    = character_varying(26)
    default = ""
  }
  column "concatenatedinviteduserids" {
    null    = true
    type    = character_varying(65535)
    default = ""
  }
  column "defaultcommanderid" {
    null    = true
    type    = character_varying(26)
    default = ""
  }
  column "announcementchannelid" {
    null    = true
    type    = character_varying(26)
    default = ""
  }
  column "concatenatedwebhookoncreationurls" {
    null    = true
    type    = character_varying(65535)
    default = ""
  }
  column "concatenatedinvitedgroupids" {
    null    = true
    type    = character_varying(65535)
    default = ""
  }
  column "retrospective" {
    null    = true
    type    = character_varying(65535)
    default = ""
  }
  column "messageonjoin" {
    null    = true
    type    = character_varying(65535)
    default = ""
  }
  column "retrospectivepublishedat" {
    null    = false
    type    = bigint
    default = 0
  }
  column "retrospectivereminderintervalseconds" {
    null    = false
    type    = bigint
    default = 0
  }
  column "retrospectivewascanceled" {
    null    = true
    type    = boolean
    default = false
  }
  column "concatenatedwebhookonstatusupdateurls" {
    null    = true
    type    = character_varying(65535)
    default = ""
  }
  column "laststatusupdateat" {
    null    = true
    type    = bigint
    default = 0
  }
  column "exportchannelonfinishedenabled" {
    null    = false
    type    = boolean
    default = false
  }
  column "categorizechannelenabled" {
    null    = true
    type    = boolean
    default = false
  }
  column "categoryname" {
    null    = true
    type    = character_varying(65535)
    default = ""
  }
  column "concatenatedbroadcastchannelids" {
    null = true
    type = character_varying(65535)
  }
  column "channelidtorootid" {
    null    = true
    type    = character_varying(65535)
    default = ""
  }
  column "remindertimerdefaultseconds" {
    null    = false
    type    = bigint
    default = 0
  }
  column "statusupdateenabled" {
    null    = true
    type    = boolean
    default = true
  }
  column "retrospectiveenabled" {
    null    = true
    type    = boolean
    default = true
  }
  column "statusupdatebroadcastchannelsenabled" {
    null    = true
    type    = boolean
    default = false
  }
  column "statusupdatebroadcastwebhooksenabled" {
    null    = true
    type    = boolean
    default = false
  }
  column "summarymodifiedat" {
    null    = false
    type    = bigint
    default = 0
  }
  column "createchannelmemberonnewparticipant" {
    null    = true
    type    = boolean
    default = true
  }
  column "removechannelmemberonremovedparticipant" {
    null    = true
    type    = boolean
    default = true
  }
  column "runtype" {
    null    = true
    type    = character_varying(32)
    default = "playbook"
  }
  primary_key {
    columns = [column.id]
  }
  index "ir_incident_channelid" {
    columns = [column.channelid]
  }
  index "ir_incident_teamid" {
    columns = [column.teamid]
  }
  index "ir_incident_teamid_commanderuserid" {
    columns = [column.teamid, column.commanderuserid]
  }
}
table "ir_metric" {
  schema = schema.public
  column "incidentid" {
    null = false
    type = character_varying(26)
  }
  column "metricconfigid" {
    null = false
    type = character_varying(26)
  }
  column "value" {
    null = true
    type = bigint
  }
  column "published" {
    null = false
    type = boolean
  }
  primary_key {
    columns = [column.incidentid, column.metricconfigid]
  }
  foreign_key "ir_metric_incidentid_fkey" {
    columns     = [column.incidentid]
    ref_columns = [table.ir_incident.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "ir_metric_metricconfigid_fkey" {
    columns     = [column.metricconfigid]
    ref_columns = [table.ir_metricconfig.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "ir_metric_incidentid" {
    columns = [column.incidentid]
  }
  index "ir_metric_metricconfigid" {
    columns = [column.metricconfigid]
  }
}
table "ir_metricconfig" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(26)
  }
  column "playbookid" {
    null = false
    type = character_varying(26)
  }
  column "title" {
    null = false
    type = character_varying(512)
  }
  column "description" {
    null = false
    type = character_varying(4096)
  }
  column "type" {
    null = false
    type = character_varying(32)
  }
  column "target" {
    null = true
    type = bigint
  }
  column "ordering" {
    null    = false
    type    = smallint
    default = 0
  }
  column "deleteat" {
    null    = false
    type    = bigint
    default = 0
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "ir_metricconfig_playbookid_fkey" {
    columns     = [column.playbookid]
    ref_columns = [table.ir_playbook.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "ir_metricconfig_playbookid" {
    columns = [column.playbookid]
  }
}
table "ir_playbook" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(26)
  }
  column "title" {
    null = false
    type = character_varying(1024)
  }
  column "description" {
    null = false
    type = character_varying(4096)
  }
  column "teamid" {
    null = false
    type = character_varying(26)
  }
  column "createpublicincident" {
    null = false
    type = boolean
  }
  column "createat" {
    null = false
    type = bigint
  }
  column "deleteat" {
    null    = false
    type    = bigint
    default = 0
  }
  column "checklistsjson" {
    null = false
    type = json
  }
  column "numstages" {
    null    = false
    type    = bigint
    default = 0
  }
  column "numsteps" {
    null    = false
    type    = bigint
    default = 0
  }
  column "broadcastchannelid" {
    null    = true
    type    = character_varying(26)
    default = ""
  }
  column "remindermessagetemplate" {
    null    = true
    type    = character_varying(65535)
    default = ""
  }
  column "remindertimerdefaultseconds" {
    null    = false
    type    = bigint
    default = 0
  }
  column "concatenatedinviteduserids" {
    null    = true
    type    = character_varying(65535)
    default = ""
  }
  column "inviteusersenabled" {
    null    = true
    type    = boolean
    default = false
  }
  column "defaultcommanderid" {
    null    = true
    type    = character_varying(26)
    default = ""
  }
  column "defaultcommanderenabled" {
    null    = true
    type    = boolean
    default = false
  }
  column "announcementchannelid" {
    null    = true
    type    = character_varying(26)
    default = ""
  }
  column "announcementchannelenabled" {
    null    = true
    type    = boolean
    default = false
  }
  column "concatenatedwebhookoncreationurls" {
    null    = true
    type    = character_varying(65535)
    default = ""
  }
  column "webhookoncreationenabled" {
    null    = true
    type    = boolean
    default = false
  }
  column "concatenatedinvitedgroupids" {
    null    = true
    type    = character_varying(65535)
    default = ""
  }
  column "messageonjoin" {
    null    = true
    type    = character_varying(65535)
    default = ""
  }
  column "messageonjoinenabled" {
    null    = true
    type    = boolean
    default = false
  }
  column "retrospectivereminderintervalseconds" {
    null    = false
    type    = bigint
    default = 0
  }
  column "retrospectivetemplate" {
    null = true
    type = character_varying(65535)
  }
  column "concatenatedwebhookonstatusupdateurls" {
    null    = true
    type    = character_varying(65535)
    default = ""
  }
  column "webhookonstatusupdateenabled" {
    null    = true
    type    = boolean
    default = false
  }
  column "concatenatedsignalanykeywords" {
    null    = true
    type    = character_varying(65535)
    default = ""
  }
  column "signalanykeywordsenabled" {
    null    = true
    type    = boolean
    default = false
  }
  column "updateat" {
    null    = false
    type    = bigint
    default = 0
  }
  column "exportchannelonfinishedenabled" {
    null    = false
    type    = boolean
    default = false
  }
  column "categorizechannelenabled" {
    null    = true
    type    = boolean
    default = false
  }
  column "categoryname" {
    null    = true
    type    = character_varying(65535)
    default = ""
  }
  column "concatenatedbroadcastchannelids" {
    null = true
    type = character_varying(65535)
  }
  column "broadcastenabled" {
    null    = true
    type    = boolean
    default = false
  }
  column "runsummarytemplate" {
    null    = true
    type    = character_varying(65535)
    default = ""
  }
  column "channelnametemplate" {
    null    = true
    type    = character_varying(65535)
    default = ""
  }
  column "statusupdateenabled" {
    null    = true
    type    = boolean
    default = true
  }
  column "retrospectiveenabled" {
    null    = true
    type    = boolean
    default = true
  }
  column "public" {
    null    = true
    type    = boolean
    default = false
  }
  column "runsummarytemplateenabled" {
    null    = true
    type    = boolean
    default = true
  }
  column "createchannelmemberonnewparticipant" {
    null    = true
    type    = boolean
    default = true
  }
  column "removechannelmemberonremovedparticipant" {
    null    = true
    type    = boolean
    default = true
  }
  column "channelid" {
    null    = true
    type    = character_varying(26)
    default = ""
  }
  column "channelmode" {
    null    = true
    type    = character_varying(32)
    default = "create_new_channel"
  }
  primary_key {
    columns = [column.id]
  }
  index "ir_playbook_teamid" {
    columns = [column.teamid]
  }
  index "ir_playbook_updateat" {
    columns = [column.updateat]
  }
}
table "ir_playbookautofollow" {
  schema = schema.public
  column "playbookid" {
    null = false
    type = character_varying(26)
  }
  column "userid" {
    null = false
    type = character_varying(26)
  }
  primary_key {
    columns = [column.playbookid, column.userid]
  }
  foreign_key "ir_playbookautofollow_playbookid_fkey" {
    columns     = [column.playbookid]
    ref_columns = [table.ir_playbook.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
}
table "ir_playbookmember" {
  schema = schema.public
  column "playbookid" {
    null = false
    type = character_varying(26)
  }
  column "memberid" {
    null = false
    type = character_varying(26)
  }
  column "roles" {
    null = true
    type = character_varying(65535)
  }
  primary_key {
    columns = [column.memberid, column.playbookid]
  }
  foreign_key "ir_playbookmember_playbookid_fkey" {
    columns     = [column.playbookid]
    ref_columns = [table.ir_playbook.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "ir_playbookmember_memberid" {
    columns = [column.memberid]
  }
  index "ir_playbookmember_playbookid" {
    columns = [column.playbookid]
  }
  unique "ir_playbookmember_playbookid_memberid_key" {
    columns = [column.playbookid, column.memberid]
  }
}
table "ir_run_participants" {
  schema = schema.public
  column "userid" {
    null = false
    type = character_varying(26)
  }
  column "incidentid" {
    null = false
    type = character_varying(26)
  }
  column "isfollower" {
    null    = false
    type    = boolean
    default = false
  }
  column "isparticipant" {
    null    = true
    type    = boolean
    default = false
  }
  primary_key {
    columns = [column.incidentid, column.userid]
  }
  foreign_key "ir_run_participants_incidentid_fkey" {
    columns     = [column.incidentid]
    ref_columns = [table.ir_incident.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "ir_run_participants_incidentid" {
    columns = [column.incidentid]
  }
  index "ir_run_participants_userid" {
    columns = [column.userid]
  }
}
table "ir_statusposts" {
  schema = schema.public
  column "incidentid" {
    null = false
    type = character_varying(26)
  }
  column "postid" {
    null = false
    type = character_varying(26)
  }
  primary_key {
    columns = [column.incidentid, column.postid]
  }
  foreign_key "ir_statusposts_incidentid_fkey" {
    columns     = [column.incidentid]
    ref_columns = [table.ir_incident.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "ir_statusposts_incidentid" {
    columns = [column.incidentid]
  }
  index "ir_statusposts_postid" {
    columns = [column.postid]
  }
  unique "ir_statusposts_incidentid_postid_key" {
    columns = [column.incidentid, column.postid]
  }
}
table "ir_system" {
  schema = schema.public
  column "skey" {
    null = false
    type = character_varying(64)
  }
  column "svalue" {
    null = true
    type = character_varying(1024)
  }
  primary_key {
    columns = [column.skey]
  }
}
table "ir_timelineevent" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(26)
  }
  column "incidentid" {
    null = false
    type = character_varying(26)
  }
  column "createat" {
    null = false
    type = bigint
  }
  column "deleteat" {
    null    = false
    type    = bigint
    default = 0
  }
  column "eventat" {
    null = false
    type = bigint
  }
  column "eventtype" {
    null    = false
    type    = character_varying(32)
    default = ""
  }
  column "summary" {
    null    = false
    type    = character_varying(256)
    default = ""
  }
  column "details" {
    null    = false
    type    = character_varying(4096)
    default = ""
  }
  column "postid" {
    null    = false
    type    = character_varying(26)
    default = ""
  }
  column "subjectuserid" {
    null    = false
    type    = character_varying(26)
    default = ""
  }
  column "creatoruserid" {
    null    = false
    type    = character_varying(26)
    default = ""
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "ir_timelineevent_incidentid_fkey" {
    columns     = [column.incidentid]
    ref_columns = [table.ir_incident.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "ir_timelineevent_id" {
    columns = [column.id]
  }
  index "ir_timelineevent_incidentid" {
    columns = [column.incidentid]
  }
}
table "ir_userinfo" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(26)
  }
  column "lastdailytododmat" {
    null = true
    type = bigint
  }
  column "digestnotificationsettingsjson" {
    null = true
    type = json
  }
  primary_key {
    columns = [column.id]
  }
}
table "ir_viewedchannel" {
  schema = schema.public
  column "channelid" {
    null = false
    type = character_varying(26)
  }
  column "userid" {
    null = false
    type = character_varying(26)
  }
  primary_key {
    columns = [column.channelid, column.userid]
  }
}
table "jobs" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(26)
  }
  column "type" {
    null = true
    type = character_varying(32)
  }
  column "priority" {
    null = true
    type = bigint
  }
  column "createat" {
    null = true
    type = bigint
  }
  column "startat" {
    null = true
    type = bigint
  }
  column "lastactivityat" {
    null = true
    type = bigint
  }
  column "status" {
    null = true
    type = character_varying(32)
  }
  column "progress" {
    null = true
    type = bigint
  }
  column "data" {
    null = true
    type = jsonb
  }
  primary_key {
    columns = [column.id]
  }
  index "idx_jobs_status_type" {
    columns = [column.status, column.type]
  }
  index "idx_jobs_type" {
    columns = [column.type]
  }
}
table "licenses" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(26)
  }
  column "createat" {
    null = true
    type = bigint
  }
  column "bytes" {
    null = true
    type = character_varying(10000)
  }
  primary_key {
    columns = [column.id]
  }
}
table "linkmetadata" {
  schema = schema.public
  column "hash" {
    null = false
    type = bigint
  }
  column "url" {
    null = true
    type = character_varying(2048)
  }
  column "timestamp" {
    null = true
    type = bigint
  }
  column "type" {
    null = true
    type = character_varying(16)
  }
  column "data" {
    null = true
    type = jsonb
  }
  primary_key {
    columns = [column.hash]
  }
  index "idx_link_metadata_url_timestamp" {
    columns = [column.url, column.timestamp]
  }
}
table "llm_postmeta" {
  schema = schema.public
  column "rootpostid" {
    null = false
    type = text
  }
  column "title" {
    null = false
    type = text
  }
  primary_key {
    columns = [column.rootpostid]
  }
  foreign_key "llm_postmeta_rootpostid_fkey" {
    columns     = [column.rootpostid]
    ref_columns = [table.posts.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
}
table "notifyadmin" {
  schema = schema.public
  column "userid" {
    null = false
    type = character_varying(26)
  }
  column "createat" {
    null = true
    type = bigint
  }
  column "requiredplan" {
    null = false
    type = character_varying(100)
  }
  column "requiredfeature" {
    null = false
    type = character_varying(255)
  }
  column "trial" {
    null = false
    type = boolean
  }
  column "sentat" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.userid, column.requiredfeature, column.requiredplan]
  }
}
table "oauthaccessdata" {
  schema = schema.public
  column "token" {
    null = false
    type = character_varying(26)
  }
  column "refreshtoken" {
    null = true
    type = character_varying(26)
  }
  column "redirecturi" {
    null = true
    type = character_varying(256)
  }
  column "clientid" {
    null = true
    type = character_varying(26)
  }
  column "userid" {
    null = true
    type = character_varying(26)
  }
  column "expiresat" {
    null = true
    type = bigint
  }
  column "scope" {
    null = true
    type = character_varying(128)
  }
  primary_key {
    columns = [column.token]
  }
  index "idx_oauthaccessdata_refresh_token" {
    columns = [column.refreshtoken]
  }
  index "idx_oauthaccessdata_user_id" {
    columns = [column.userid]
  }
  unique "oauthaccessdata_clientid_userid_key" {
    columns = [column.clientid, column.userid]
  }
}
table "oauthapps" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(26)
  }
  column "creatorid" {
    null = true
    type = character_varying(26)
  }
  column "createat" {
    null = true
    type = bigint
  }
  column "updateat" {
    null = true
    type = bigint
  }
  column "clientsecret" {
    null = true
    type = character_varying(128)
  }
  column "name" {
    null = true
    type = character_varying(64)
  }
  column "description" {
    null = true
    type = character_varying(512)
  }
  column "callbackurls" {
    null = true
    type = character_varying(1024)
  }
  column "homepage" {
    null = true
    type = character_varying(256)
  }
  column "istrusted" {
    null = true
    type = boolean
  }
  column "iconurl" {
    null = true
    type = character_varying(512)
  }
  column "mattermostappid" {
    null    = false
    type    = character_varying(32)
    default = ""
  }
  primary_key {
    columns = [column.id]
  }
  index "idx_oauthapps_creator_id" {
    columns = [column.creatorid]
  }
}
table "oauthauthdata" {
  schema = schema.public
  column "clientid" {
    null = true
    type = character_varying(26)
  }
  column "userid" {
    null = true
    type = character_varying(26)
  }
  column "code" {
    null = false
    type = character_varying(128)
  }
  column "expiresin" {
    null = true
    type = integer
  }
  column "createat" {
    null = true
    type = bigint
  }
  column "redirecturi" {
    null = true
    type = character_varying(256)
  }
  column "state" {
    null = true
    type = character_varying(1024)
  }
  column "scope" {
    null = true
    type = character_varying(128)
  }
  primary_key {
    columns = [column.code]
  }
}
table "outgoingoauthconnections" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(26)
  }
  column "name" {
    null = true
    type = character_varying(64)
  }
  column "creatorid" {
    null = true
    type = character_varying(26)
  }
  column "createat" {
    null = true
    type = bigint
  }
  column "updateat" {
    null = true
    type = bigint
  }
  column "clientid" {
    null = true
    type = character_varying(255)
  }
  column "clientsecret" {
    null = true
    type = character_varying(255)
  }
  column "credentialsusername" {
    null = true
    type = character_varying(255)
  }
  column "credentialspassword" {
    null = true
    type = character_varying(255)
  }
  column "oauthtokenurl" {
    null = true
    type = text
  }
  column "granttype" {
    null    = true
    type    = enum.outgoingoauthconnections_granttype
    default = "client_credentials"
  }
  column "audiences" {
    null = true
    type = character_varying(1024)
  }
  primary_key {
    columns = [column.id]
  }
  index "idx_outgoingoauthconnections_name" {
    columns = [column.name]
  }
}
table "outgoingwebhooks" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(26)
  }
  column "token" {
    null = true
    type = character_varying(26)
  }
  column "createat" {
    null = true
    type = bigint
  }
  column "updateat" {
    null = true
    type = bigint
  }
  column "deleteat" {
    null = true
    type = bigint
  }
  column "creatorid" {
    null = true
    type = character_varying(26)
  }
  column "channelid" {
    null = true
    type = character_varying(26)
  }
  column "teamid" {
    null = true
    type = character_varying(26)
  }
  column "triggerwords" {
    null = true
    type = character_varying(1024)
  }
  column "callbackurls" {
    null = true
    type = character_varying(1024)
  }
  column "displayname" {
    null = true
    type = character_varying(64)
  }
  column "contenttype" {
    null = true
    type = character_varying(128)
  }
  column "triggerwhen" {
    null = true
    type = integer
  }
  column "username" {
    null = true
    type = character_varying(64)
  }
  column "iconurl" {
    null = true
    type = character_varying(1024)
  }
  column "description" {
    null = true
    type = character_varying(500)
  }
  primary_key {
    columns = [column.id]
  }
  index "idx_outgoing_webhook_create_at" {
    columns = [column.createat]
  }
  index "idx_outgoing_webhook_delete_at" {
    columns = [column.deleteat]
  }
  index "idx_outgoing_webhook_team_id" {
    columns = [column.teamid]
  }
  index "idx_outgoing_webhook_update_at" {
    columns = [column.updateat]
  }
}
table "persistentnotifications" {
  schema = schema.public
  column "postid" {
    null = false
    type = character_varying(26)
  }
  column "createat" {
    null = true
    type = bigint
  }
  column "lastsentat" {
    null = true
    type = bigint
  }
  column "deleteat" {
    null = true
    type = bigint
  }
  column "sentcount" {
    null = true
    type = smallint
  }
  primary_key {
    columns = [column.postid]
  }
}
table "pluginkeyvaluestore" {
  schema = schema.public
  column "pluginid" {
    null = false
    type = character_varying(190)
  }
  column "pkey" {
    null = false
    type = character_varying(150)
  }
  column "pvalue" {
    null = true
    type = bytea
  }
  column "expireat" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.pluginid, column.pkey]
  }
}
table "postacknowledgements" {
  schema = schema.public
  column "postid" {
    null = false
    type = character_varying(26)
  }
  column "userid" {
    null = false
    type = character_varying(26)
  }
  column "acknowledgedat" {
    null = true
    type = bigint
  }
  column "remoteid" {
    null    = true
    type    = character_varying(26)
    default = ""
  }
  column "channelid" {
    null    = true
    type    = character_varying(26)
    default = ""
  }
  primary_key {
    columns = [column.postid, column.userid]
  }
}
table "postreminders" {
  schema = schema.public
  column "postid" {
    null = false
    type = character_varying(26)
  }
  column "userid" {
    null = false
    type = character_varying(26)
  }
  column "targettime" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.postid, column.userid]
  }
  index "idx_postreminders_targettime" {
    columns = [column.targettime]
  }
}
table "posts" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(26)
  }
  column "createat" {
    null = true
    type = bigint
  }
  column "updateat" {
    null = true
    type = bigint
  }
  column "deleteat" {
    null = true
    type = bigint
  }
  column "userid" {
    null = true
    type = character_varying(26)
  }
  column "channelid" {
    null = true
    type = character_varying(26)
  }
  column "rootid" {
    null = true
    type = character_varying(26)
  }
  column "originalid" {
    null = true
    type = character_varying(26)
  }
  column "message" {
    null = true
    type = character_varying(65535)
  }
  column "type" {
    null = true
    type = character_varying(26)
  }
  column "props" {
    null = true
    type = jsonb
  }
  column "hashtags" {
    null = true
    type = character_varying(1000)
  }
  column "filenames" {
    null = true
    type = character_varying(4000)
  }
  column "fileids" {
    null = true
    type = character_varying(300)
  }
  column "hasreactions" {
    null = true
    type = boolean
  }
  column "editat" {
    null = true
    type = bigint
  }
  column "ispinned" {
    null = true
    type = boolean
  }
  column "remoteid" {
    null = true
    type = character_varying(26)
  }
  primary_key {
    columns = [column.id]
  }
  index "idx_posts_channel_id_delete_at_create_at" {
    columns = [column.channelid, column.deleteat, column.createat]
  }
  index "idx_posts_channel_id_update_at" {
    columns = [column.channelid, column.updateat]
  }
  index "idx_posts_create_at" {
    columns = [column.createat]
  }
  index "idx_posts_create_at_id" {
    columns = [column.createat, column.id]
  }
  index "idx_posts_delete_at" {
    columns = [column.deleteat]
  }
  index "idx_posts_hashtags_txt" {
    type = GIN
    on {
      expr = "to_tsvector('english'::regconfig, (hashtags)::text)"
    }
  }
  index "idx_posts_is_pinned" {
    columns = [column.ispinned]
  }
  index "idx_posts_message_txt" {
    type = GIN
    on {
      expr = "to_tsvector('english'::regconfig, (message)::text)"
    }
  }
  index "idx_posts_original_id" {
    columns = [column.originalid]
  }
  index "idx_posts_root_id_delete_at" {
    columns = [column.rootid, column.deleteat]
  }
  index "idx_posts_update_at" {
    columns = [column.updateat]
  }
  index "idx_posts_user_id" {
    columns = [column.userid]
  }
}
table "postspriority" {
  schema = schema.public
  column "postid" {
    null = false
    type = character_varying(26)
  }
  column "channelid" {
    null = false
    type = character_varying(26)
  }
  column "priority" {
    null = false
    type = character_varying(32)
  }
  column "requestedack" {
    null = true
    type = boolean
  }
  column "persistentnotifications" {
    null = true
    type = boolean
  }
  primary_key {
    columns = [column.postid]
  }
}
table "preferences" {
  schema = schema.public
  column "userid" {
    null = false
    type = character_varying(26)
  }
  column "category" {
    null = false
    type = character_varying(32)
  }
  column "name" {
    null = false
    type = character_varying(32)
  }
  column "value" {
    null = true
    type = text
  }
  primary_key {
    columns = [column.userid, column.category, column.name]
  }
  index "idx_preferences_category" {
    columns = [column.category]
  }
  index "idx_preferences_name" {
    columns = [column.name]
  }
}
table "productnoticeviewstate" {
  schema = schema.public
  column "userid" {
    null = false
    type = character_varying(26)
  }
  column "noticeid" {
    null = false
    type = character_varying(26)
  }
  column "viewed" {
    null = true
    type = integer
  }
  column "timestamp" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.userid, column.noticeid]
  }
  index "idx_notice_views_notice_id" {
    columns = [column.noticeid]
  }
  index "idx_notice_views_timestamp" {
    columns = [column.timestamp]
  }
}
table "propertyfields" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(26)
  }
  column "groupid" {
    null = false
    type = character_varying(26)
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "type" {
    null = true
    type = enum.property_field_type
  }
  column "attrs" {
    null = true
    type = jsonb
  }
  column "targetid" {
    null = true
    type = character_varying(255)
  }
  column "targettype" {
    null = true
    type = character_varying(255)
  }
  column "createat" {
    null = false
    type = bigint
  }
  column "updateat" {
    null = false
    type = bigint
  }
  column "deleteat" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  index "idx_propertyfields_create_at_id" {
    columns = [column.createat, column.id]
  }
  index "idx_propertyfields_unique" {
    unique  = true
    columns = [column.groupid, column.targetid, column.name]
    where   = "(deleteat = 0)"
  }
}
table "propertygroups" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(26)
  }
  column "name" {
    null = false
    type = character_varying(64)
  }
  primary_key {
    columns = [column.id]
  }
  unique "propertygroups_name_key" {
    columns = [column.name]
  }
}
table "propertyvalues" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(26)
  }
  column "targetid" {
    null = false
    type = character_varying(255)
  }
  column "targettype" {
    null = false
    type = character_varying(255)
  }
  column "groupid" {
    null = false
    type = character_varying(26)
  }
  column "fieldid" {
    null = false
    type = character_varying(26)
  }
  column "value" {
    null = false
    type = jsonb
  }
  column "createat" {
    null = false
    type = bigint
  }
  column "updateat" {
    null = false
    type = bigint
  }
  column "deleteat" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  index "idx_propertyvalues_create_at_id" {
    columns = [column.createat, column.id]
  }
  index "idx_propertyvalues_targetid_groupid" {
    columns = [column.targetid, column.groupid]
  }
  index "idx_propertyvalues_unique" {
    unique  = true
    columns = [column.groupid, column.targetid, column.fieldid]
    where   = "(deleteat = 0)"
  }
}
table "publicchannels" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(26)
  }
  column "deleteat" {
    null = true
    type = bigint
  }
  column "teamid" {
    null = true
    type = character_varying(26)
  }
  column "displayname" {
    null = true
    type = character_varying(64)
  }
  column "name" {
    null = true
    type = character_varying(64)
  }
  column "header" {
    null = true
    type = character_varying(1024)
  }
  column "purpose" {
    null = true
    type = character_varying(250)
  }
  primary_key {
    columns = [column.id]
  }
  index "idx_publicchannels_delete_at" {
    columns = [column.deleteat]
  }
  index "idx_publicchannels_displayname_lower" {
    on {
      expr = "lower((displayname)::text)"
    }
  }
  index "idx_publicchannels_name_lower" {
    on {
      expr = "lower((name)::text)"
    }
  }
  index "idx_publicchannels_search_txt" {
    type = GIN
    on {
      expr = "to_tsvector('english'::regconfig, (((((name)::text || ' '::text) || (displayname)::text) || ' '::text) || (purpose)::text))"
    }
  }
  index "idx_publicchannels_team_id" {
    columns = [column.teamid]
  }
  unique "publicchannels_name_teamid_key" {
    columns = [column.name, column.teamid]
  }
}
table "reactions" {
  schema = schema.public
  column "userid" {
    null = false
    type = character_varying(26)
  }
  column "postid" {
    null = false
    type = character_varying(26)
  }
  column "emojiname" {
    null = false
    type = character_varying(64)
  }
  column "createat" {
    null = true
    type = bigint
  }
  column "updateat" {
    null = true
    type = bigint
  }
  column "deleteat" {
    null = true
    type = bigint
  }
  column "remoteid" {
    null = true
    type = character_varying(26)
  }
  column "channelid" {
    null    = false
    type    = character_varying(26)
    default = ""
  }
  primary_key {
    columns = [column.postid, column.userid, column.emojiname]
  }
  index "idx_reactions_channel_id" {
    columns = [column.channelid]
  }
}
table "recentsearches" {
  schema = schema.public
  column "userid" {
    null = false
    type = character(26)
  }
  column "searchpointer" {
    null = false
    type = integer
  }
  column "query" {
    null = true
    type = jsonb
  }
  column "createat" {
    null = false
    type = bigint
  }
  primary_key {
    columns = [column.userid, column.searchpointer]
  }
}
table "remoteclusters" {
  schema = schema.public
  column "remoteid" {
    null = false
    type = character_varying(26)
  }
  column "remoteteamid" {
    null = true
    type = character_varying(26)
  }
  column "name" {
    null = false
    type = character_varying(64)
  }
  column "displayname" {
    null = true
    type = character_varying(64)
  }
  column "siteurl" {
    null = true
    type = character_varying(512)
  }
  column "createat" {
    null = true
    type = bigint
  }
  column "lastpingat" {
    null = true
    type = bigint
  }
  column "token" {
    null = true
    type = character_varying(26)
  }
  column "remotetoken" {
    null = true
    type = character_varying(26)
  }
  column "topics" {
    null = true
    type = character_varying(512)
  }
  column "creatorid" {
    null = true
    type = character_varying(26)
  }
  column "pluginid" {
    null    = false
    type    = character_varying(190)
    default = ""
  }
  column "options" {
    null    = false
    type    = smallint
    default = 0
  }
  column "defaultteamid" {
    null    = true
    type    = character_varying(26)
    default = ""
  }
  column "deleteat" {
    null    = true
    type    = bigint
    default = 0
  }
  column "lastglobalusersyncat" {
    null    = true
    type    = bigint
    default = 0
  }
  primary_key {
    columns = [column.remoteid, column.name]
  }
}
table "retentionidsfordeletion" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(26)
  }
  column "tablename" {
    null = true
    type = character_varying(64)
  }
  column "ids" {
    null = true
    type = sql("character varying(26)[]")
  }
  primary_key {
    columns = [column.id]
  }
  index "idx_retentionidsfordeletion_tablename" {
    columns = [column.tablename]
  }
}
table "retentionpolicies" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(26)
  }
  column "displayname" {
    null = true
    type = character_varying(64)
  }
  column "postduration" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  index "idx_retentionpolicies_displayname" {
    columns = [column.displayname]
  }
}
table "retentionpolicieschannels" {
  schema = schema.public
  column "policyid" {
    null = true
    type = character_varying(26)
  }
  column "channelid" {
    null = false
    type = character_varying(26)
  }
  primary_key {
    columns = [column.channelid]
  }
  foreign_key "fk_retentionpolicieschannels_retentionpolicies" {
    columns     = [column.policyid]
    ref_columns = [table.retentionpolicies.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  index "idx_retentionpolicieschannels_policyid" {
    columns = [column.policyid]
  }
}
table "retentionpoliciesteams" {
  schema = schema.public
  column "policyid" {
    null = true
    type = character_varying(26)
  }
  column "teamid" {
    null = false
    type = character_varying(26)
  }
  primary_key {
    columns = [column.teamid]
  }
  foreign_key "fk_retentionpoliciesteams_retentionpolicies" {
    columns     = [column.policyid]
    ref_columns = [table.retentionpolicies.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  index "idx_retentionpoliciesteams_policyid" {
    columns = [column.policyid]
  }
}
table "roles" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(26)
  }
  column "name" {
    null = true
    type = character_varying(64)
  }
  column "displayname" {
    null = true
    type = character_varying(128)
  }
  column "description" {
    null = true
    type = character_varying(1024)
  }
  column "createat" {
    null = true
    type = bigint
  }
  column "updateat" {
    null = true
    type = bigint
  }
  column "deleteat" {
    null = true
    type = bigint
  }
  column "permissions" {
    null = true
    type = text
  }
  column "schememanaged" {
    null = true
    type = boolean
  }
  column "builtin" {
    null = true
    type = boolean
  }
  primary_key {
    columns = [column.id]
  }
  unique "roles_name_key" {
    columns = [column.name]
  }
}
table "scheduledposts" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(26)
  }
  column "createat" {
    null = true
    type = bigint
  }
  column "updateat" {
    null = true
    type = bigint
  }
  column "userid" {
    null = false
    type = character_varying(26)
  }
  column "channelid" {
    null = false
    type = character_varying(26)
  }
  column "rootid" {
    null = true
    type = character_varying(26)
  }
  column "message" {
    null = true
    type = character_varying(65535)
  }
  column "props" {
    null = true
    type = character_varying(8000)
  }
  column "fileids" {
    null = true
    type = character_varying(300)
  }
  column "priority" {
    null = true
    type = text
  }
  column "scheduledat" {
    null = false
    type = bigint
  }
  column "processedat" {
    null = true
    type = bigint
  }
  column "errorcode" {
    null = true
    type = character_varying(200)
  }
  primary_key {
    columns = [column.id]
  }
  index "idx_scheduledposts_userid_channel_id_scheduled_at" {
    columns = [column.userid, column.channelid, column.scheduledat]
  }
}
table "schemes" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(26)
  }
  column "name" {
    null = true
    type = character_varying(64)
  }
  column "displayname" {
    null = true
    type = character_varying(128)
  }
  column "description" {
    null = true
    type = character_varying(1024)
  }
  column "createat" {
    null = true
    type = bigint
  }
  column "updateat" {
    null = true
    type = bigint
  }
  column "deleteat" {
    null = true
    type = bigint
  }
  column "scope" {
    null = true
    type = character_varying(32)
  }
  column "defaultteamadminrole" {
    null = true
    type = character_varying(64)
  }
  column "defaultteamuserrole" {
    null = true
    type = character_varying(64)
  }
  column "defaultchanneladminrole" {
    null = true
    type = character_varying(64)
  }
  column "defaultchanneluserrole" {
    null = true
    type = character_varying(64)
  }
  column "defaultteamguestrole" {
    null = true
    type = character_varying(64)
  }
  column "defaultchannelguestrole" {
    null = true
    type = character_varying(64)
  }
  column "defaultplaybookadminrole" {
    null    = true
    type    = character_varying(64)
    default = ""
  }
  column "defaultplaybookmemberrole" {
    null    = true
    type    = character_varying(64)
    default = ""
  }
  column "defaultrunadminrole" {
    null    = true
    type    = character_varying(64)
    default = ""
  }
  column "defaultrunmemberrole" {
    null    = true
    type    = character_varying(64)
    default = ""
  }
  primary_key {
    columns = [column.id]
  }
  index "idx_schemes_channel_admin_role" {
    columns = [column.defaultchanneladminrole]
  }
  index "idx_schemes_channel_guest_role" {
    columns = [column.defaultchannelguestrole]
  }
  index "idx_schemes_channel_user_role" {
    columns = [column.defaultchanneluserrole]
  }
  unique "schemes_name_key" {
    columns = [column.name]
  }
}
table "sessions" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(26)
  }
  column "token" {
    null = true
    type = character_varying(26)
  }
  column "createat" {
    null = true
    type = bigint
  }
  column "expiresat" {
    null = true
    type = bigint
  }
  column "lastactivityat" {
    null = true
    type = bigint
  }
  column "userid" {
    null = true
    type = character_varying(26)
  }
  column "deviceid" {
    null = true
    type = character_varying(512)
  }
  column "roles" {
    null = true
    type = character_varying(256)
  }
  column "isoauth" {
    null = true
    type = boolean
  }
  column "props" {
    null = true
    type = jsonb
  }
  column "expirednotify" {
    null = true
    type = boolean
  }
  primary_key {
    columns = [column.id]
  }
  index "idx_sessions_create_at" {
    columns = [column.createat]
  }
  index "idx_sessions_expires_at" {
    columns = [column.expiresat]
  }
  index "idx_sessions_last_activity_at" {
    columns = [column.lastactivityat]
  }
  index "idx_sessions_token" {
    columns = [column.token]
  }
  index "idx_sessions_user_id" {
    columns = [column.userid]
  }
}
table "sharedchannelattachments" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(26)
  }
  column "fileid" {
    null = true
    type = character_varying(26)
  }
  column "remoteid" {
    null = true
    type = character_varying(26)
  }
  column "createat" {
    null = true
    type = bigint
  }
  column "lastsyncat" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.id]
  }
  unique "sharedchannelattachments_fileid_remoteid_key" {
    columns = [column.fileid, column.remoteid]
  }
}
table "sharedchannelremotes" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(26)
  }
  column "channelid" {
    null = false
    type = character_varying(26)
  }
  column "creatorid" {
    null = true
    type = character_varying(26)
  }
  column "createat" {
    null = true
    type = bigint
  }
  column "updateat" {
    null = true
    type = bigint
  }
  column "isinviteaccepted" {
    null = true
    type = boolean
  }
  column "isinviteconfirmed" {
    null = true
    type = boolean
  }
  column "remoteid" {
    null = true
    type = character_varying(26)
  }
  column "lastpostupdateat" {
    null = true
    type = bigint
  }
  column "lastpostid" {
    null = true
    type = character_varying(26)
  }
  column "lastpostcreateat" {
    null    = false
    type    = bigint
    default = 0
  }
  column "lastpostcreateid" {
    null = true
    type = character_varying(26)
  }
  column "deleteat" {
    null    = true
    type    = bigint
    default = 0
  }
  column "lastmemberssyncat" {
    null    = true
    type    = bigint
    default = 0
  }
  primary_key {
    columns = [column.id, column.channelid]
  }
  unique "sharedchannelremotes_channelid_remoteid_key" {
    columns = [column.channelid, column.remoteid]
  }
}
table "sharedchannels" {
  schema = schema.public
  column "channelid" {
    null = false
    type = character_varying(26)
  }
  column "teamid" {
    null = true
    type = character_varying(26)
  }
  column "home" {
    null = true
    type = boolean
  }
  column "readonly" {
    null = true
    type = boolean
  }
  column "sharename" {
    null = true
    type = character_varying(64)
  }
  column "sharedisplayname" {
    null = true
    type = character_varying(64)
  }
  column "sharepurpose" {
    null = true
    type = character_varying(250)
  }
  column "shareheader" {
    null = true
    type = character_varying(1024)
  }
  column "creatorid" {
    null = true
    type = character_varying(26)
  }
  column "createat" {
    null = true
    type = bigint
  }
  column "updateat" {
    null = true
    type = bigint
  }
  column "remoteid" {
    null = true
    type = character_varying(26)
  }
  primary_key {
    columns = [column.channelid]
  }
  unique "sharedchannels_sharename_teamid_key" {
    columns = [column.sharename, column.teamid]
  }
}
table "sharedchannelusers" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(26)
  }
  column "userid" {
    null = true
    type = character_varying(26)
  }
  column "remoteid" {
    null = true
    type = character_varying(26)
  }
  column "createat" {
    null = true
    type = bigint
  }
  column "lastsyncat" {
    null = true
    type = bigint
  }
  column "channelid" {
    null = true
    type = character_varying(26)
  }
  column "lastmembershipsyncat" {
    null    = true
    type    = bigint
    default = 0
  }
  primary_key {
    columns = [column.id]
  }
  index "idx_sharedchannelusers_remote_id" {
    columns = [column.remoteid]
  }
  unique "sharedchannelusers_userid_channelid_remoteid_key" {
    columns = [column.userid, column.channelid, column.remoteid]
  }
}
table "sidebarcategories" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(128)
  }
  column "userid" {
    null = true
    type = character_varying(26)
  }
  column "teamid" {
    null = true
    type = character_varying(26)
  }
  column "sortorder" {
    null = true
    type = bigint
  }
  column "sorting" {
    null = true
    type = character_varying(64)
  }
  column "type" {
    null = true
    type = character_varying(64)
  }
  column "displayname" {
    null = true
    type = character_varying(64)
  }
  column "muted" {
    null = true
    type = boolean
  }
  column "collapsed" {
    null = true
    type = boolean
  }
  primary_key {
    columns = [column.id]
  }
  index "idx_sidebarcategories_userid_teamid" {
    columns = [column.userid, column.teamid]
  }
}
table "sidebarchannels" {
  schema = schema.public
  column "channelid" {
    null = false
    type = character_varying(26)
  }
  column "userid" {
    null = false
    type = character_varying(26)
  }
  column "categoryid" {
    null = false
    type = character_varying(128)
  }
  column "sortorder" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.channelid, column.userid, column.categoryid]
  }
  index "idx_sidebarchannels_categoryid" {
    columns = [column.categoryid]
  }
}
table "status" {
  schema = schema.public
  column "userid" {
    null = false
    type = character_varying(26)
  }
  column "status" {
    null = true
    type = character_varying(32)
  }
  column "manual" {
    null = true
    type = boolean
  }
  column "lastactivityat" {
    null = true
    type = bigint
  }
  column "dndendtime" {
    null = true
    type = bigint
  }
  column "prevstatus" {
    null = true
    type = character_varying(32)
  }
  primary_key {
    columns = [column.userid]
  }
  index "idx_status_status_dndendtime" {
    columns = [column.status, column.dndendtime]
  }
}
table "systems" {
  schema = schema.public
  column "name" {
    null = false
    type = character_varying(64)
  }
  column "value" {
    null = true
    type = character_varying(1024)
  }
  primary_key {
    columns = [column.name]
  }
}
table "teammembers" {
  schema = schema.public
  column "teamid" {
    null = false
    type = character_varying(26)
  }
  column "userid" {
    null = false
    type = character_varying(26)
  }
  column "roles" {
    null = true
    type = character_varying(256)
  }
  column "deleteat" {
    null = true
    type = bigint
  }
  column "schemeuser" {
    null = true
    type = boolean
  }
  column "schemeadmin" {
    null = true
    type = boolean
  }
  column "schemeguest" {
    null = true
    type = boolean
  }
  column "createat" {
    null    = true
    type    = bigint
    default = 0
  }
  primary_key {
    columns = [column.teamid, column.userid]
  }
  index "idx_teammembers_createat" {
    columns = [column.createat]
  }
  index "idx_teammembers_delete_at" {
    columns = [column.deleteat]
  }
  index "idx_teammembers_user_id" {
    columns = [column.userid]
  }
}
table "teams" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(26)
  }
  column "createat" {
    null = true
    type = bigint
  }
  column "updateat" {
    null = true
    type = bigint
  }
  column "deleteat" {
    null = true
    type = bigint
  }
  column "displayname" {
    null = true
    type = character_varying(64)
  }
  column "name" {
    null = true
    type = character_varying(64)
  }
  column "description" {
    null = true
    type = character_varying(255)
  }
  column "email" {
    null = true
    type = character_varying(128)
  }
  column "type" {
    null = true
    type = enum.team_type
  }
  column "companyname" {
    null = true
    type = character_varying(64)
  }
  column "alloweddomains" {
    null = true
    type = character_varying(1000)
  }
  column "inviteid" {
    null = true
    type = character_varying(32)
  }
  column "schemeid" {
    null = true
    type = character_varying(26)
  }
  column "allowopeninvite" {
    null = true
    type = boolean
  }
  column "lastteamiconupdate" {
    null = true
    type = bigint
  }
  column "groupconstrained" {
    null = true
    type = boolean
  }
  column "cloudlimitsarchived" {
    null    = false
    type    = boolean
    default = false
  }
  primary_key {
    columns = [column.id]
  }
  index "idx_teams_create_at" {
    columns = [column.createat]
  }
  index "idx_teams_delete_at" {
    columns = [column.deleteat]
  }
  index "idx_teams_invite_id" {
    columns = [column.inviteid]
  }
  index "idx_teams_scheme_id" {
    columns = [column.schemeid]
  }
  index "idx_teams_update_at" {
    columns = [column.updateat]
  }
  unique "teams_name_key" {
    columns = [column.name]
  }
}
table "termsofservice" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(26)
  }
  column "createat" {
    null = true
    type = bigint
  }
  column "userid" {
    null = true
    type = character_varying(26)
  }
  column "text" {
    null = true
    type = character_varying(65535)
  }
  primary_key {
    columns = [column.id]
  }
}
table "threadmemberships" {
  schema = schema.public
  column "postid" {
    null = false
    type = character_varying(26)
  }
  column "userid" {
    null = false
    type = character_varying(26)
  }
  column "following" {
    null = true
    type = boolean
  }
  column "lastviewed" {
    null = true
    type = bigint
  }
  column "lastupdated" {
    null = true
    type = bigint
  }
  column "unreadmentions" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.postid, column.userid]
  }
  index "idx_thread_memberships_last_update_at" {
    columns = [column.lastupdated]
  }
  index "idx_thread_memberships_last_view_at" {
    columns = [column.lastviewed]
  }
  index "idx_thread_memberships_user_id" {
    columns = [column.userid]
  }
}
table "threads" {
  schema = schema.public
  column "postid" {
    null = false
    type = character_varying(26)
  }
  column "replycount" {
    null = true
    type = bigint
  }
  column "lastreplyat" {
    null = true
    type = bigint
  }
  column "participants" {
    null = true
    type = jsonb
  }
  column "channelid" {
    null = true
    type = character_varying(26)
  }
  column "threaddeleteat" {
    null = true
    type = bigint
  }
  column "threadteamid" {
    null = true
    type = character_varying(26)
  }
  primary_key {
    columns = [column.postid]
  }
  index "idx_threads_channel_id_last_reply_at" {
    columns = [column.channelid, column.lastreplyat]
  }
}
table "tokens" {
  schema = schema.public
  column "token" {
    null = false
    type = character_varying(64)
  }
  column "createat" {
    null = true
    type = bigint
  }
  column "type" {
    null = true
    type = character_varying(64)
  }
  column "extra" {
    null = true
    type = character_varying(2048)
  }
  primary_key {
    columns = [column.token]
  }
}
table "uploadsessions" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(26)
  }
  column "type" {
    null = true
    type = enum.upload_session_type
  }
  column "createat" {
    null = true
    type = bigint
  }
  column "userid" {
    null = true
    type = character_varying(26)
  }
  column "channelid" {
    null = true
    type = character_varying(26)
  }
  column "filename" {
    null = true
    type = character_varying(256)
  }
  column "path" {
    null = true
    type = character_varying(512)
  }
  column "filesize" {
    null = true
    type = bigint
  }
  column "fileoffset" {
    null = true
    type = bigint
  }
  column "remoteid" {
    null = true
    type = character_varying(26)
  }
  column "reqfileid" {
    null = true
    type = character_varying(26)
  }
  primary_key {
    columns = [column.id]
  }
  index "idx_uploadsessions_create_at" {
    columns = [column.createat]
  }
  index "idx_uploadsessions_type" {
    columns = [column.type]
  }
  index "idx_uploadsessions_user_id" {
    columns = [column.userid]
  }
}
table "useraccesstokens" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(26)
  }
  column "token" {
    null = true
    type = character_varying(26)
  }
  column "userid" {
    null = true
    type = character_varying(26)
  }
  column "description" {
    null = true
    type = character_varying(512)
  }
  column "isactive" {
    null = true
    type = boolean
  }
  primary_key {
    columns = [column.id]
  }
  index "idx_user_access_tokens_user_id" {
    columns = [column.userid]
  }
  unique "useraccesstokens_token_key" {
    columns = [column.token]
  }
}
table "usergroups" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(26)
  }
  column "name" {
    null = true
    type = character_varying(64)
  }
  column "displayname" {
    null = true
    type = character_varying(128)
  }
  column "description" {
    null = true
    type = character_varying(1024)
  }
  column "source" {
    null = true
    type = character_varying(64)
  }
  column "remoteid" {
    null = true
    type = character_varying(48)
  }
  column "createat" {
    null = true
    type = bigint
  }
  column "updateat" {
    null = true
    type = bigint
  }
  column "deleteat" {
    null = true
    type = bigint
  }
  column "allowreference" {
    null = true
    type = boolean
  }
  primary_key {
    columns = [column.id]
  }
  index "idx_usergroups_delete_at" {
    columns = [column.deleteat]
  }
  index "idx_usergroups_displayname" {
    columns = [column.displayname]
  }
  index "idx_usergroups_remote_id" {
    columns = [column.remoteid]
  }
  unique "usergroups_name_key" {
    columns = [column.name]
  }
  unique "usergroups_source_remoteid_key" {
    columns = [column.source, column.remoteid]
  }
}
table "users" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(26)
  }
  column "createat" {
    null = true
    type = bigint
  }
  column "updateat" {
    null = true
    type = bigint
  }
  column "deleteat" {
    null = true
    type = bigint
  }
  column "username" {
    null = true
    type = character_varying(64)
  }
  column "password" {
    null = true
    type = character_varying(128)
  }
  column "authdata" {
    null = true
    type = character_varying(128)
  }
  column "authservice" {
    null = true
    type = character_varying(32)
  }
  column "email" {
    null = true
    type = character_varying(128)
  }
  column "emailverified" {
    null = true
    type = boolean
  }
  column "nickname" {
    null = true
    type = character_varying(64)
  }
  column "firstname" {
    null = true
    type = character_varying(64)
  }
  column "lastname" {
    null = true
    type = character_varying(64)
  }
  column "roles" {
    null = true
    type = character_varying(256)
  }
  column "allowmarketing" {
    null = true
    type = boolean
  }
  column "props" {
    null = true
    type = jsonb
  }
  column "notifyprops" {
    null = true
    type = jsonb
  }
  column "lastpasswordupdate" {
    null = true
    type = bigint
  }
  column "lastpictureupdate" {
    null = true
    type = bigint
  }
  column "failedattempts" {
    null = true
    type = integer
  }
  column "locale" {
    null = true
    type = character_varying(5)
  }
  column "mfaactive" {
    null = true
    type = boolean
  }
  column "mfasecret" {
    null = true
    type = character_varying(128)
  }
  column "position" {
    null = true
    type = character_varying(128)
  }
  column "timezone" {
    null = true
    type = jsonb
  }
  column "remoteid" {
    null = true
    type = character_varying(26)
  }
  column "lastlogin" {
    null    = false
    type    = bigint
    default = 0
  }
  column "mfausedtimestamps" {
    null = true
    type = jsonb
  }
  primary_key {
    columns = [column.id]
  }
  index "idx_users_all_no_full_name_txt" {
    type = GIN
    on {
      expr = "to_tsvector('english'::regconfig, (((((username)::text || ' '::text) || (nickname)::text) || ' '::text) || (email)::text))"
    }
  }
  index "idx_users_all_txt" {
    type = GIN
    on {
      expr = "to_tsvector('english'::regconfig, (((((((((username)::text || ' '::text) || (firstname)::text) || ' '::text) || (lastname)::text) || ' '::text) || (nickname)::text) || ' '::text) || (email)::text))"
    }
  }
  index "idx_users_create_at" {
    columns = [column.createat]
  }
  index "idx_users_delete_at" {
    columns = [column.deleteat]
  }
  index "idx_users_email_lower_textpattern" {
    on {
      expr = "lower((email)::text)"
      ops  = text_pattern_ops
    }
  }
  index "idx_users_firstname_lower_textpattern" {
    on {
      expr = "lower((firstname)::text)"
      ops  = text_pattern_ops
    }
  }
  index "idx_users_lastname_lower_textpattern" {
    on {
      expr = "lower((lastname)::text)"
      ops  = text_pattern_ops
    }
  }
  index "idx_users_names_no_full_name_txt" {
    type = GIN
    on {
      expr = "to_tsvector('english'::regconfig, (((username)::text || ' '::text) || (nickname)::text))"
    }
  }
  index "idx_users_names_txt" {
    type = GIN
    on {
      expr = "to_tsvector('english'::regconfig, (((((((username)::text || ' '::text) || (firstname)::text) || ' '::text) || (lastname)::text) || ' '::text) || (nickname)::text))"
    }
  }
  index "idx_users_nickname_lower_textpattern" {
    on {
      expr = "lower((nickname)::text)"
      ops  = text_pattern_ops
    }
  }
  index "idx_users_update_at" {
    columns = [column.updateat]
  }
  index "idx_users_username_lower_textpattern" {
    on {
      expr = "lower((username)::text)"
      ops  = text_pattern_ops
    }
  }
  unique "users_authdata_key" {
    columns = [column.authdata]
  }
  unique "users_email_key" {
    columns = [column.email]
  }
  unique "users_username_key" {
    columns = [column.username]
  }
}
table "usertermsofservice" {
  schema = schema.public
  column "userid" {
    null = false
    type = character_varying(26)
  }
  column "termsofserviceid" {
    null = true
    type = character_varying(26)
  }
  column "createat" {
    null = true
    type = bigint
  }
  primary_key {
    columns = [column.userid]
  }
}
enum "channel_type" {
  schema = schema.public
  values = ["P", "G", "O", "D"]
}
enum "team_type" {
  schema = schema.public
  values = ["I", "O"]
}
enum "upload_session_type" {
  schema = schema.public
  values = ["attachment", "import"]
}
enum "outgoingoauthconnections_granttype" {
  schema = schema.public
  values = ["client_credentials", "password"]
}
enum "channel_bookmark_type" {
  schema = schema.public
  values = ["link", "file"]
}
enum "property_field_type" {
  schema = schema.public
  values = ["text", "select", "multiselect", "date", "user", "multiuser"]
}
schema "public" {
  comment = "standard public schema"
}
