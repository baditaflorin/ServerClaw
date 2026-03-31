Notice: This Atlas edition lacks support for features such as checkpoints,
testing, down migrations, and more. Additionally, advanced database objects such as views,
triggers, and stored procedures are not supported. To read more: https://atlasgo.io/community-edition

To install the non-community version of Atlas, use the following command:

	curl -sSf https://atlasgo.sh | sh

Or, visit the website to see all installation options:

	https://atlasgo.io/docs#installation

table "assertion" {
  schema = schema.public
  column "store" {
    null = false
    type = text
  }
  column "authorization_model_id" {
    null = false
    type = text
  }
  column "assertions" {
    null = true
    type = bytea
  }
  primary_key {
    columns = [column.store, column.authorization_model_id]
  }
}
table "authorization_model" {
  schema = schema.public
  column "store" {
    null = false
    type = text
  }
  column "authorization_model_id" {
    null = false
    type = text
  }
  column "type" {
    null = false
    type = text
  }
  column "type_definition" {
    null = true
    type = bytea
  }
  column "schema_version" {
    null    = false
    type    = text
    default = "1.0"
  }
  column "serialized_protobuf" {
    null = true
    type = bytea
  }
  primary_key {
    columns = [column.store, column.authorization_model_id, column.type]
  }
}
table "changelog" {
  schema = schema.public
  column "store" {
    null = false
    type = text
  }
  column "object_type" {
    null = false
    type = text
  }
  column "object_id" {
    null = false
    type = text
  }
  column "relation" {
    null = false
    type = text
  }
  column "_user" {
    null = false
    type = text
  }
  column "operation" {
    null = false
    type = integer
  }
  column "ulid" {
    null = false
    type = text
  }
  column "inserted_at" {
    null = false
    type = timestamptz
  }
  column "condition_name" {
    null = true
    type = text
  }
  column "condition_context" {
    null = true
    type = bytea
  }
  primary_key {
    columns = [column.store, column.ulid, column.object_type]
  }
}
table "goose_db_version" {
  schema = schema.public
  column "id" {
    null = false
    type = integer
    identity {
      generated = BY_DEFAULT
    }
  }
  column "version_id" {
    null = false
    type = bigint
  }
  column "is_applied" {
    null = false
    type = boolean
  }
  column "tstamp" {
    null    = false
    type    = timestamp
    default = sql("now()")
  }
  primary_key {
    columns = [column.id]
  }
}
table "store" {
  schema = schema.public
  column "id" {
    null = false
    type = text
  }
  column "name" {
    null = false
    type = text
  }
  column "created_at" {
    null = false
    type = timestamptz
  }
  column "updated_at" {
    null = true
    type = timestamptz
  }
  column "deleted_at" {
    null = true
    type = timestamptz
  }
  primary_key {
    columns = [column.id]
  }
}
table "tuple" {
  schema = schema.public
  column "store" {
    null = false
    type = text
  }
  column "object_type" {
    null = false
    type = text
  }
  column "object_id" {
    null = false
    type = text
  }
  column "relation" {
    null = false
    type = text
  }
  column "_user" {
    null = false
    type = text
  }
  column "user_type" {
    null = false
    type = text
  }
  column "ulid" {
    null = false
    type = text
  }
  column "inserted_at" {
    null = false
    type = timestamptz
  }
  column "condition_name" {
    null = true
    type = text
  }
  column "condition_context" {
    null = true
    type = bytea
  }
  primary_key {
    columns = [column.store, column.object_type, column.object_id, column.relation, column._user]
  }
  index "idx_tuple_partial_user" {
    columns = [column.store, column.object_type, column.object_id, column.relation, column._user]
    where   = "(user_type = 'user'::text)"
  }
  index "idx_tuple_partial_userset" {
    columns = [column.store, column.object_type, column.object_id, column.relation, column._user]
    where   = "(user_type = 'userset'::text)"
  }
  index "idx_tuple_ulid" {
    unique  = true
    columns = [column.ulid]
  }
  index "idx_user_lookup" {
    columns = [column.store, column._user, column.relation, column.object_type, column.object_id]
  }
}
schema "public" {
  comment = "standard public schema"
}
