Notice: This Atlas edition lacks support for features such as checkpoints,
testing, down migrations, and more. Additionally, advanced database objects such as views,
triggers, and stored procedures are not supported. To read more: https://atlasgo.io/community-edition

To install the non-community version of Atlas, use the following command:

	curl -sSf https://atlasgo.sh | sh

Or, visit the website to see all installation options:

	https://atlasgo.io/docs#installation

table "SequelizeMeta" {
  schema = schema.public
  column "name" {
    null = false
    type = character_varying(255)
  }
  primary_key {
    columns = [column.name]
  }
}
table "apiKeys" {
  schema = schema.public
  column "id" {
    null = false
    type = uuid
  }
  column "name" {
    null = true
    type = character_varying
  }
  column "secret" {
    null = true
    type = character_varying(255)
  }
  column "userId" {
    null = true
    type = uuid
  }
  column "createdAt" {
    null = false
    type = timestamptz
  }
  column "updatedAt" {
    null = false
    type = timestamptz
  }
  column "deletedAt" {
    null = true
    type = timestamptz
  }
  column "expiresAt" {
    null = true
    type = timestamptz
  }
  column "lastActiveAt" {
    null = true
    type = timestamptz
  }
  column "hash" {
    null = true
    type = character_varying(255)
  }
  column "last4" {
    null = true
    type = character_varying(4)
  }
  column "scope" {
    null = true
    type = sql("character varying(255)[]")
  }
  primary_key {
    columns = [column.id]
  }
  index "api_keys_user_id_deleted_at" {
    columns = [column.userId, column.deletedAt]
  }
  unique "apiKeys_hash_key" {
    columns = [column.hash]
  }
  unique "apiKeys_secret_key" {
    columns = [column.secret]
  }
}
table "attachments" {
  schema = schema.public
  column "id" {
    null = false
    type = uuid
  }
  column "teamId" {
    null = false
    type = uuid
  }
  column "userId" {
    null = false
    type = uuid
  }
  column "documentId" {
    null = true
    type = uuid
  }
  column "key" {
    null = false
    type = character_varying(4096)
  }
  column "contentType" {
    null = false
    type = character_varying(255)
  }
  column "size" {
    null = false
    type = bigint
  }
  column "acl" {
    null = false
    type = character_varying(255)
  }
  column "createdAt" {
    null = false
    type = timestamptz
  }
  column "updatedAt" {
    null = false
    type = timestamptz
  }
  column "lastAccessedAt" {
    null = true
    type = timestamptz
  }
  column "expiresAt" {
    null = true
    type = timestamptz
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "attachments_teamId_fkey" {
    columns     = [column.teamId]
    ref_columns = [table.teams.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "attachments_userId_fkey" {
    columns     = [column.userId]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "attachments_created_at" {
    columns = [column.createdAt]
  }
  index "attachments_document_id" {
    columns = [column.documentId]
  }
  index "attachments_expires_at" {
    columns = [column.expiresAt]
  }
  index "attachments_team_id" {
    columns = [column.teamId]
  }
}
table "authentication_providers" {
  schema = schema.public
  column "id" {
    null = false
    type = uuid
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "providerId" {
    null = false
    type = character_varying(255)
  }
  column "enabled" {
    null    = false
    type    = boolean
    default = true
  }
  column "teamId" {
    null = false
    type = uuid
  }
  column "createdAt" {
    null = false
    type = timestamptz
  }
  column "settings" {
    null = true
    type = jsonb
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "authentication_providers_teamId_fkey" {
    columns     = [column.teamId]
    ref_columns = [table.teams.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "authentication_providers_provider_id" {
    columns = [column.providerId]
  }
  unique "authentication_providers_providerId_teamId_uk" {
    columns = [column.providerId, column.teamId]
  }
}
table "authentications" {
  schema = schema.public
  column "id" {
    null = false
    type = uuid
  }
  column "userId" {
    null = true
    type = uuid
  }
  column "teamId" {
    null = true
    type = uuid
  }
  column "service" {
    null = false
    type = character_varying(255)
  }
  column "token" {
    null = true
    type = bytea
  }
  column "scopes" {
    null = true
    type = sql("character varying(255)[]")
  }
  column "createdAt" {
    null = false
    type = timestamptz
  }
  column "updatedAt" {
    null = false
    type = timestamptz
  }
  column "refreshToken" {
    null = true
    type = bytea
  }
  column "expiresAt" {
    null = true
    type = timestamptz
  }
  column "clientId" {
    null = true
    type = character_varying(255)
  }
  column "clientSecret" {
    null = true
    type = bytea
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "authentications_teamId_fkey" {
    columns     = [column.teamId]
    ref_columns = [table.teams.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "authentications_userId_fkey" {
    columns     = [column.userId]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "authentications_team_id_service" {
    columns = [column.teamId, column.service]
  }
}
table "collections" {
  schema = schema.public
  column "id" {
    null = false
    type = uuid
  }
  column "name" {
    null = true
    type = character_varying
  }
  column "description" {
    null = true
    type = character_varying
  }
  column "createdAt" {
    null = false
    type = timestamptz
  }
  column "updatedAt" {
    null = false
    type = timestamptz
  }
  column "teamId" {
    null = false
    type = uuid
  }
  column "searchVector" {
    null = true
    type = tsvector
  }
  column "createdById" {
    null = true
    type = uuid
  }
  column "deletedAt" {
    null = true
    type = timestamptz
  }
  column "urlId" {
    null = true
    type = character_varying(255)
  }
  column "documentStructure" {
    null = true
    type = jsonb
  }
  column "color" {
    null = true
    type = text
  }
  column "maintainerApprovalRequired" {
    null    = false
    type    = boolean
    default = false
  }
  column "icon" {
    null = true
    type = text
  }
  column "sort" {
    null = true
    type = jsonb
  }
  column "sharing" {
    null    = false
    type    = boolean
    default = true
  }
  column "index" {
    null = true
    type = text
  }
  column "permission" {
    null    = true
    type    = character_varying(255)
    default = sql("NULL::character varying")
  }
  column "state" {
    null = true
    type = bytea
  }
  column "importId" {
    null = true
    type = uuid
  }
  column "content" {
    null = true
    type = jsonb
  }
  column "archivedAt" {
    null = true
    type = timestamptz
  }
  column "archivedById" {
    null = true
    type = uuid
  }
  column "apiImportId" {
    null = true
    type = uuid
  }
  column "commenting" {
    null = true
    type = boolean
  }
  column "sourceMetadata" {
    null = true
    type = jsonb
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "collections_apiImportId_fkey" {
    columns     = [column.apiImportId]
    ref_columns = [table.imports.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "collections_archivedById_fkey" {
    columns     = [column.archivedById]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "collections_importId_fkey" {
    columns     = [column.importId]
    ref_columns = [table.file_operations.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "collections_api_import_id" {
    columns = [column.apiImportId]
  }
  index "collections_archived_at" {
    columns = [column.archivedAt]
  }
  index "collections_import_id" {
    columns = [column.importId]
  }
  index "collections_team_id_deleted_at" {
    columns = [column.teamId, column.deletedAt]
  }
  unique "atlases_urlId_key" {
    columns = [column.urlId]
  }
}
table "comments" {
  schema = schema.public
  column "id" {
    null = false
    type = uuid
  }
  column "data" {
    null = false
    type = jsonb
  }
  column "documentId" {
    null = false
    type = uuid
  }
  column "parentCommentId" {
    null = true
    type = uuid
  }
  column "createdById" {
    null = false
    type = uuid
  }
  column "resolvedAt" {
    null = true
    type = timestamptz
  }
  column "resolvedById" {
    null = true
    type = uuid
  }
  column "createdAt" {
    null = false
    type = timestamptz
  }
  column "updatedAt" {
    null = false
    type = timestamptz
  }
  column "deletedAt" {
    null = true
    type = timestamptz
  }
  column "reactions" {
    null = true
    type = jsonb
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "comments_createdById_fkey" {
    columns     = [column.createdById]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "comments_documentId_fkey" {
    columns     = [column.documentId]
    ref_columns = [table.documents.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "comments_parentCommentId_fkey" {
    columns     = [column.parentCommentId]
    ref_columns = [table.comments.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "comments_resolvedById_fkey" {
    columns     = [column.resolvedById]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = SET_NULL
  }
  index "comments_created_at" {
    columns = [column.createdAt]
  }
  index "comments_document_id" {
    columns = [column.documentId]
  }
}
table "documents" {
  schema = schema.public
  column "id" {
    null = false
    type = uuid
  }
  column "urlId" {
    null = false
    type = character_varying
  }
  column "title" {
    null = false
    type = character_varying
  }
  column "text" {
    null = true
    type = text
  }
  column "createdAt" {
    null = false
    type = timestamptz
  }
  column "updatedAt" {
    null = false
    type = timestamptz
  }
  column "collectionId" {
    null = true
    type = uuid
  }
  column "teamId" {
    null = true
    type = uuid
  }
  column "parentDocumentId" {
    null = true
    type = uuid
  }
  column "lastModifiedById" {
    null = false
    type = uuid
  }
  column "revisionCount" {
    null    = true
    type    = integer
    default = 0
  }
  column "searchVector" {
    null = true
    type = tsvector
  }
  column "deletedAt" {
    null = true
    type = timestamptz
  }
  column "createdById" {
    null = true
    type = uuid
  }
  column "collaboratorIds" {
    null = true
    type = sql("uuid[]")
  }
  column "publishedAt" {
    null = true
    type = timestamptz
  }
  column "pinnedById" {
    null = true
    type = uuid
  }
  column "archivedAt" {
    null = true
    type = timestamptz
  }
  column "isWelcome" {
    null    = false
    type    = boolean
    default = false
  }
  column "editorVersion" {
    null = true
    type = character_varying(255)
  }
  column "version" {
    null = true
    type = smallint
  }
  column "template" {
    null    = false
    type    = boolean
    default = false
  }
  column "templateId" {
    null = true
    type = uuid
  }
  column "previousTitles" {
    null = true
    type = sql("character varying(255)[]")
  }
  column "state" {
    null = true
    type = bytea
  }
  column "fullWidth" {
    null    = false
    type    = boolean
    default = false
  }
  column "importId" {
    null = true
    type = uuid
  }
  column "insightsEnabled" {
    null    = false
    type    = boolean
    default = true
  }
  column "sourceMetadata" {
    null = true
    type = jsonb
  }
  column "content" {
    null = true
    type = jsonb
  }
  column "summary" {
    null = true
    type = text
  }
  column "icon" {
    null = true
    type = character_varying(255)
  }
  column "color" {
    null = true
    type = character_varying(255)
  }
  column "apiImportId" {
    null = true
    type = uuid
  }
  column "language" {
    null = true
    type = character_varying(2)
  }
  column "popularityScore" {
    null    = false
    type    = double_precision
    default = 0
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "documents_apiImportId_fkey" {
    columns     = [column.apiImportId]
    ref_columns = [table.imports.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "documents_atlasId_fkey" {
    columns     = [column.collectionId]
    ref_columns = [table.collections.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "documents_createdById_fkey" {
    columns     = [column.createdById]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "documents_importId_fkey" {
    columns     = [column.importId]
    ref_columns = [table.file_operations.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "documents_lastModifiedById_fkey" {
    columns     = [column.lastModifiedById]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "documents_parentDocumentId_fkey" {
    columns     = [column.parentDocumentId]
    ref_columns = [table.documents.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "documents_teamId_fkey" {
    columns     = [column.teamId]
    ref_columns = [table.teams.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  index "documents_api_import_id" {
    columns = [column.apiImportId]
  }
  index "documents_archived_at" {
    columns = [column.archivedAt]
  }
  index "documents_collection_id" {
    columns = [column.collectionId]
  }
  index "documents_import_id" {
    columns = [column.importId]
  }
  index "documents_parent_document_id_atlas_id_deleted_at" {
    columns = [column.parentDocumentId, column.collectionId, column.deletedAt]
  }
  index "documents_published_at" {
    columns = [column.publishedAt]
  }
  index "documents_team_id" {
    columns = [column.teamId, column.deletedAt]
  }
  index "documents_title_idx" {
    type = GIN
    on {
      column = column.title
      ops    = gin_trgm_ops
    }
  }
  index "documents_tsv_idx" {
    columns = [column.searchVector]
    type    = GIN
  }
  index "documents_updated_at" {
    columns = [column.updatedAt]
  }
  index "documents_url_id_deleted_at" {
    columns = [column.urlId, column.deletedAt]
  }
  unique "documents_urlId_key" {
    columns = [column.urlId]
  }
}
table "emojis" {
  schema = schema.public
  column "id" {
    null = false
    type = uuid
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "attachmentId" {
    null = false
    type = uuid
  }
  column "teamId" {
    null = false
    type = uuid
  }
  column "createdById" {
    null = false
    type = uuid
  }
  column "createdAt" {
    null = false
    type = timestamptz
  }
  column "updatedAt" {
    null = false
    type = timestamptz
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "emojis_attachmentId_fkey" {
    columns     = [column.attachmentId]
    ref_columns = [table.attachments.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "emojis_createdById_fkey" {
    columns     = [column.createdById]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "emojis_teamId_fkey" {
    columns     = [column.teamId]
    ref_columns = [table.teams.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  index "emojis_attachment_id" {
    columns = [column.attachmentId]
  }
  index "emojis_created_by_id" {
    columns = [column.createdById]
  }
  index "emojis_team_id" {
    columns = [column.teamId]
  }
  index "emojis_team_id_name" {
    unique  = true
    columns = [column.teamId, column.name]
  }
}
table "events" {
  schema = schema.public
  column "id" {
    null = false
    type = uuid
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "data" {
    null = true
    type = jsonb
  }
  column "userId" {
    null = true
    type = uuid
  }
  column "collectionId" {
    null = true
    type = uuid
  }
  column "teamId" {
    null = true
    type = uuid
  }
  column "createdAt" {
    null = false
    type = timestamptz
  }
  column "documentId" {
    null = true
    type = uuid
  }
  column "actorId" {
    null = true
    type = uuid
  }
  column "modelId" {
    null = true
    type = uuid
  }
  column "ip" {
    null = true
    type = character_varying(255)
  }
  column "changes" {
    null = true
    type = jsonb
  }
  column "authType" {
    null = true
    type = character_varying(255)
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "events_actorId_fkey" {
    columns     = [column.actorId]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "events_collectionId_fkey" {
    columns     = [column.collectionId]
    ref_columns = [table.collections.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "events_teamId_fkey" {
    columns     = [column.teamId]
    ref_columns = [table.teams.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "events_userId_fkey" {
    columns     = [column.userId]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "events_actor_id" {
    columns = [column.actorId]
  }
  index "events_created_at" {
    columns = [column.createdAt]
  }
  index "events_document_id" {
    columns = [column.documentId]
  }
  index "events_name" {
    columns = [column.name]
  }
  index "events_team_id_collection_id" {
    columns = [column.teamId, column.collectionId]
  }
}
table "external_groups" {
  schema = schema.public
  column "id" {
    null = false
    type = uuid
  }
  column "externalId" {
    null = false
    type = character_varying(255)
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "groupId" {
    null = true
    type = uuid
  }
  column "authenticationProviderId" {
    null = false
    type = uuid
  }
  column "teamId" {
    null = false
    type = uuid
  }
  column "lastSyncedAt" {
    null = true
    type = timestamptz
  }
  column "createdAt" {
    null = false
    type = timestamptz
  }
  column "updatedAt" {
    null = false
    type = timestamptz
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "external_groups_authenticationProviderId_fkey" {
    columns     = [column.authenticationProviderId]
    ref_columns = [table.authentication_providers.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "external_groups_groupId_fkey" {
    columns     = [column.groupId]
    ref_columns = [table.groups.column.id]
    on_update   = NO_ACTION
    on_delete   = SET_NULL
  }
  foreign_key "external_groups_teamId_fkey" {
    columns     = [column.teamId]
    ref_columns = [table.teams.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  index "external_groups_authentication_provider_id_external_id" {
    unique  = true
    columns = [column.authenticationProviderId, column.externalId]
  }
}
table "file_operations" {
  schema = schema.public
  column "id" {
    null = false
    type = uuid
  }
  column "state" {
    null = false
    type = enum.enum_file_operations_state
  }
  column "type" {
    null = false
    type = enum.enum_file_operations_type
  }
  column "key" {
    null = true
    type = character_varying(255)
  }
  column "url" {
    null = true
    type = character_varying(255)
  }
  column "size" {
    null = false
    type = bigint
  }
  column "userId" {
    null = false
    type = uuid
  }
  column "collectionId" {
    null = true
    type = uuid
  }
  column "teamId" {
    null = false
    type = uuid
  }
  column "createdAt" {
    null = false
    type = timestamptz
  }
  column "updatedAt" {
    null = false
    type = timestamptz
  }
  column "error" {
    null = true
    type = character_varying(255)
  }
  column "format" {
    null    = false
    type    = character_varying(255)
    default = "outline-markdown"
  }
  column "includeAttachments" {
    null    = false
    type    = boolean
    default = true
  }
  column "deletedAt" {
    null = true
    type = timestamptz
  }
  column "options" {
    null = true
    type = jsonb
  }
  column "documentId" {
    null = true
    type = uuid
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "file_operations_collectionId_fkey" {
    columns     = [column.collectionId]
    ref_columns = [table.collections.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "file_operations_documentId_fkey" {
    columns     = [column.documentId]
    ref_columns = [table.documents.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "file_operations_teamId_fkey" {
    columns     = [column.teamId]
    ref_columns = [table.teams.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "file_operations_userId_fkey" {
    columns     = [column.userId]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "file_operations_type_state" {
    columns = [column.type, column.state]
  }
}
table "group_permissions" {
  schema = schema.public
  column "collectionId" {
    null = true
    type = uuid
  }
  column "groupId" {
    null = false
    type = uuid
  }
  column "createdById" {
    null = false
    type = uuid
  }
  column "permission" {
    null = false
    type = character_varying(255)
  }
  column "createdAt" {
    null = false
    type = timestamptz
  }
  column "updatedAt" {
    null = false
    type = timestamptz
  }
  column "deletedAt" {
    null = true
    type = timestamptz
  }
  column "documentId" {
    null = true
    type = uuid
  }
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v4()")
  }
  column "sourceId" {
    null = true
    type = uuid
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "group_permissions_collectionId_fkey" {
    columns     = [column.collectionId]
    ref_columns = [table.collections.column.id]
    on_update   = NO_ACTION
    on_delete   = SET_NULL
  }
  foreign_key "group_permissions_createdById_fkey" {
    columns     = [column.createdById]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = SET_NULL
  }
  foreign_key "group_permissions_documentId_fkey" {
    columns     = [column.documentId]
    ref_columns = [table.documents.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "group_permissions_groupId_fkey" {
    columns     = [column.groupId]
    ref_columns = [table.groups.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "group_permissions_sourceId_fkey" {
    columns     = [column.sourceId]
    ref_columns = [table.group_permissions.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  index "group_permissions_collection_id_group_id" {
    columns = [column.collectionId, column.groupId]
  }
  index "group_permissions_deleted_at" {
    columns = [column.deletedAt]
  }
  index "group_permissions_document_id" {
    columns = [column.documentId]
  }
  index "group_permissions_group_id" {
    columns = [column.groupId]
  }
  index "group_permissions_source_id" {
    columns = [column.sourceId]
  }
}
table "group_users" {
  schema = schema.public
  column "userId" {
    null = false
    type = uuid
  }
  column "groupId" {
    null = false
    type = uuid
  }
  column "createdById" {
    null = false
    type = uuid
  }
  column "createdAt" {
    null = false
    type = timestamptz
  }
  column "updatedAt" {
    null = false
    type = timestamptz
  }
  column "permission" {
    null    = false
    type    = enum.enum_group_users_permission
    default = "member"
  }
  primary_key {
    columns = [column.groupId, column.userId]
  }
  foreign_key "group_users_createdById_fkey" {
    columns     = [column.createdById]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "group_users_groupId_fkey" {
    columns     = [column.groupId]
    ref_columns = [table.groups.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "group_users_userId_fkey" {
    columns     = [column.userId]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  index "group_users_user_id" {
    columns = [column.userId]
  }
}
table "groups" {
  schema = schema.public
  column "id" {
    null = false
    type = uuid
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "teamId" {
    null = false
    type = uuid
  }
  column "createdById" {
    null = false
    type = uuid
  }
  column "createdAt" {
    null = false
    type = timestamptz
  }
  column "updatedAt" {
    null = false
    type = timestamptz
  }
  column "deletedAt" {
    null = true
    type = timestamptz
  }
  column "externalId" {
    null = true
    type = character_varying(255)
  }
  column "disableMentions" {
    null    = false
    type    = boolean
    default = false
  }
  column "description" {
    null = true
    type = text
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "groups_createdById_fkey" {
    columns     = [column.createdById]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "groups_teamId_fkey" {
    columns     = [column.teamId]
    ref_columns = [table.teams.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "groups_external_id" {
    columns = [column.externalId]
  }
  index "groups_team_id" {
    columns = [column.teamId]
  }
}
table "import_tasks" {
  schema = schema.public
  column "id" {
    null = false
    type = uuid
  }
  column "state" {
    null = false
    type = character_varying(255)
  }
  column "input" {
    null = false
    type = jsonb
  }
  column "output" {
    null = true
    type = jsonb
  }
  column "importId" {
    null = false
    type = uuid
  }
  column "createdAt" {
    null = false
    type = timestamptz
  }
  column "updatedAt" {
    null = false
    type = timestamptz
  }
  column "error" {
    null = true
    type = character_varying(255)
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "import_tasks_importId_fkey" {
    columns     = [column.importId]
    ref_columns = [table.imports.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  index "import_tasks_import_id" {
    columns = [column.importId]
  }
  index "import_tasks_state_import_id" {
    columns = [column.state, column.importId]
  }
}
table "imports" {
  schema = schema.public
  column "id" {
    null = false
    type = uuid
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "service" {
    null = false
    type = character_varying(255)
  }
  column "state" {
    null = false
    type = character_varying(255)
  }
  column "input" {
    null = false
    type = jsonb
  }
  column "documentCount" {
    null    = false
    type    = integer
    default = 0
  }
  column "integrationId" {
    null = false
    type = uuid
  }
  column "createdById" {
    null = false
    type = uuid
  }
  column "teamId" {
    null = false
    type = uuid
  }
  column "createdAt" {
    null = false
    type = timestamptz
  }
  column "updatedAt" {
    null = false
    type = timestamptz
  }
  column "deletedAt" {
    null = true
    type = timestamptz
  }
  column "error" {
    null = true
    type = character_varying(255)
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "imports_createdById_fkey" {
    columns     = [column.createdById]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "imports_integrationId_fkey" {
    columns     = [column.integrationId]
    ref_columns = [table.integrations.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "imports_teamId_fkey" {
    columns     = [column.teamId]
    ref_columns = [table.teams.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "imports_service_team_id" {
    columns = [column.service, column.teamId]
  }
  index "imports_state_team_id" {
    columns = [column.state, column.teamId]
  }
}
table "integrations" {
  schema = schema.public
  column "id" {
    null = false
    type = uuid
  }
  column "type" {
    null = true
    type = character_varying(255)
  }
  column "userId" {
    null = true
    type = uuid
  }
  column "teamId" {
    null = false
    type = uuid
  }
  column "service" {
    null = false
    type = character_varying(255)
  }
  column "collectionId" {
    null = true
    type = uuid
  }
  column "authenticationId" {
    null = true
    type = uuid
  }
  column "events" {
    null = true
    type = sql("character varying(255)[]")
  }
  column "settings" {
    null = true
    type = jsonb
  }
  column "createdAt" {
    null = false
    type = timestamptz
  }
  column "updatedAt" {
    null = false
    type = timestamptz
  }
  column "deletedAt" {
    null = true
    type = timestamptz
  }
  column "issueSources" {
    null = true
    type = jsonb
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "integrations_authenticationId_fkey" {
    columns     = [column.authenticationId]
    ref_columns = [table.authentications.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "integrations_collectionId_fkey" {
    columns     = [column.collectionId]
    ref_columns = [table.collections.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "integrations_teamId_fkey" {
    columns     = [column.teamId]
    ref_columns = [table.teams.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "integrations_userId_fkey" {
    columns     = [column.userId]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "integrations_service_type" {
    columns = [column.service, column.type]
  }
  index "integrations_service_type_createdAt" {
    columns = [column.service, column.type, column.createdAt]
  }
  index "integrations_settings_slack_gin" {
    type  = GIN
    where = "(((service)::text = 'slack'::text) AND ((type)::text = 'linkedAccount'::text))"
    on {
      expr = "((settings -> 'slack'::text))"
    }
  }
  index "integrations_team_id_type_service" {
    columns = [column.teamId, column.type, column.service]
  }
}
table "notifications" {
  schema = schema.public
  column "id" {
    null = false
    type = uuid
  }
  column "actorId" {
    null = true
    type = uuid
  }
  column "userId" {
    null = false
    type = uuid
  }
  column "event" {
    null = true
    type = character_varying(255)
  }
  column "createdAt" {
    null = false
    type = timestamptz
  }
  column "viewedAt" {
    null = true
    type = timestamptz
  }
  column "emailedAt" {
    null = true
    type = timestamptz
  }
  column "teamId" {
    null = false
    type = uuid
  }
  column "documentId" {
    null = true
    type = uuid
  }
  column "commentId" {
    null = true
    type = uuid
  }
  column "revisionId" {
    null = true
    type = uuid
  }
  column "collectionId" {
    null = true
    type = uuid
  }
  column "archivedAt" {
    null = true
    type = timestamptz
  }
  column "membershipId" {
    null = true
    type = uuid
  }
  column "data" {
    null = true
    type = json
  }
  column "groupId" {
    null = true
    type = uuid
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "notifications_actorId_fkey" {
    columns     = [column.actorId]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = SET_NULL
  }
  foreign_key "notifications_collectionId_fkey" {
    columns     = [column.collectionId]
    ref_columns = [table.collections.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "notifications_commentId_fkey" {
    columns     = [column.commentId]
    ref_columns = [table.comments.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "notifications_documentId_fkey" {
    columns     = [column.documentId]
    ref_columns = [table.documents.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "notifications_groupId_fkey" {
    columns     = [column.groupId]
    ref_columns = [table.groups.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "notifications_revisionId_fkey" {
    columns     = [column.revisionId]
    ref_columns = [table.revisions.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "notifications_teamId_fkey" {
    columns     = [column.teamId]
    ref_columns = [table.teams.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "notifications_userId_fkey" {
    columns     = [column.userId]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  index "notifications_created_at" {
    columns = [column.createdAt]
  }
  index "notifications_document_id_user_id" {
    columns = [column.documentId, column.userId]
  }
  index "notifications_emailed_at" {
    columns = [column.emailedAt]
  }
  index "notifications_event" {
    columns = [column.event]
  }
  index "notifications_team_id_user_id" {
    columns = [column.teamId, column.userId]
  }
}
table "oauth_authentications" {
  schema = schema.public
  column "id" {
    null = false
    type = uuid
  }
  column "accessTokenHash" {
    null = false
    type = character_varying(255)
  }
  column "accessTokenExpiresAt" {
    null = false
    type = timestamptz
  }
  column "refreshTokenHash" {
    null = false
    type = character_varying(255)
  }
  column "refreshTokenExpiresAt" {
    null = false
    type = timestamptz
  }
  column "lastActiveAt" {
    null = true
    type = timestamptz
  }
  column "scope" {
    null = false
    type = sql("character varying(255)[]")
  }
  column "oauthClientId" {
    null = false
    type = uuid
  }
  column "userId" {
    null = false
    type = uuid
  }
  column "createdAt" {
    null = false
    type = timestamptz
  }
  column "updatedAt" {
    null = false
    type = timestamptz
  }
  column "deletedAt" {
    null = true
    type = timestamptz
  }
  column "grantId" {
    null = true
    type = uuid
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "oauth_authentications_oauthClientId_fkey" {
    columns     = [column.oauthClientId]
    ref_columns = [table.oauth_clients.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "oauth_authentications_userId_fkey" {
    columns     = [column.userId]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  index "oauth_authentications_grant_id" {
    columns = [column.grantId]
  }
  unique "oauth_authentications_accessTokenHash_key" {
    columns = [column.accessTokenHash]
  }
  unique "oauth_authentications_refreshTokenHash_key" {
    columns = [column.refreshTokenHash]
  }
}
table "oauth_authorization_codes" {
  schema = schema.public
  column "id" {
    null = false
    type = uuid
  }
  column "authorizationCodeHash" {
    null = false
    type = character_varying(255)
  }
  column "codeChallenge" {
    null = true
    type = character_varying(255)
  }
  column "codeChallengeMethod" {
    null = true
    type = character_varying(255)
  }
  column "scope" {
    null = false
    type = sql("character varying(255)[]")
  }
  column "oauthClientId" {
    null = false
    type = uuid
  }
  column "userId" {
    null = false
    type = uuid
  }
  column "redirectUri" {
    null = false
    type = character_varying(255)
  }
  column "expiresAt" {
    null = false
    type = timestamptz
  }
  column "createdAt" {
    null = false
    type = timestamptz
  }
  column "grantId" {
    null = true
    type = uuid
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "oauth_authorization_codes_oauthClientId_fkey" {
    columns     = [column.oauthClientId]
    ref_columns = [table.oauth_clients.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "oauth_authorization_codes_userId_fkey" {
    columns     = [column.userId]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  index "oauth_authorization_codes_grant_id" {
    columns = [column.grantId]
  }
}
table "oauth_clients" {
  schema = schema.public
  column "id" {
    null = false
    type = uuid
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "description" {
    null = true
    type = character_varying(255)
  }
  column "developerName" {
    null = true
    type = character_varying(255)
  }
  column "developerUrl" {
    null = true
    type = character_varying(255)
  }
  column "avatarUrl" {
    null = true
    type = character_varying(255)
  }
  column "clientId" {
    null = false
    type = character_varying(255)
  }
  column "clientSecret" {
    null = false
    type = bytea
  }
  column "published" {
    null    = false
    type    = boolean
    default = false
  }
  column "teamId" {
    null = false
    type = uuid
  }
  column "createdById" {
    null = true
    type = uuid
  }
  column "redirectUris" {
    null    = false
    type    = sql("character varying(255)[]")
    default = sql("(ARRAY[]::character varying[])::character varying(255)[]")
  }
  column "createdAt" {
    null = false
    type = timestamptz
  }
  column "updatedAt" {
    null = false
    type = timestamptz
  }
  column "deletedAt" {
    null = true
    type = timestamptz
  }
  column "clientType" {
    null    = false
    type    = character_varying(255)
    default = "confidential"
  }
  column "lastActiveAt" {
    null = true
    type = timestamptz
  }
  column "registrationAccessTokenHash" {
    null = true
    type = character_varying(255)
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "oauth_clients_createdById_fkey" {
    columns     = [column.createdById]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "oauth_clients_teamId_fkey" {
    columns     = [column.teamId]
    ref_columns = [table.teams.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  index "oauth_clients_team_id" {
    columns = [column.teamId]
  }
  unique "oauth_clients_clientId_key" {
    columns = [column.clientId]
  }
  unique "oauth_clients_registrationAccessTokenHash_key" {
    columns = [column.registrationAccessTokenHash]
  }
}
table "pins" {
  schema = schema.public
  column "id" {
    null = false
    type = uuid
  }
  column "documentId" {
    null = false
    type = uuid
  }
  column "collectionId" {
    null = true
    type = uuid
  }
  column "teamId" {
    null = false
    type = uuid
  }
  column "createdById" {
    null = false
    type = uuid
  }
  column "index" {
    null = true
    type = character_varying(255)
  }
  column "createdAt" {
    null = false
    type = timestamptz
  }
  column "updatedAt" {
    null = false
    type = timestamptz
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "pins_collectionId_fkey" {
    columns     = [column.collectionId]
    ref_columns = [table.collections.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "pins_createdById_fkey" {
    columns     = [column.createdById]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "pins_documentId_fkey" {
    columns     = [column.documentId]
    ref_columns = [table.documents.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "pins_teamId_fkey" {
    columns     = [column.teamId]
    ref_columns = [table.teams.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  index "pins_collection_id" {
    columns = [column.collectionId]
  }
  index "pins_team_id" {
    columns = [column.teamId]
  }
}
table "reactions" {
  schema = schema.public
  column "id" {
    null = false
    type = uuid
  }
  column "emoji" {
    null = false
    type = character_varying(255)
  }
  column "userId" {
    null = false
    type = uuid
  }
  column "commentId" {
    null = false
    type = uuid
  }
  column "createdAt" {
    null = false
    type = timestamptz
  }
  column "updatedAt" {
    null = false
    type = timestamptz
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "reactions_commentId_fkey" {
    columns     = [column.commentId]
    ref_columns = [table.comments.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "reactions_userId_fkey" {
    columns     = [column.userId]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  index "reactions_comment_id" {
    columns = [column.commentId]
  }
  index "reactions_emoji_user_id" {
    columns = [column.emoji, column.userId]
  }
}
table "relationships" {
  schema = schema.public
  column "id" {
    null = false
    type = uuid
  }
  column "userId" {
    null = false
    type = uuid
  }
  column "documentId" {
    null = false
    type = uuid
  }
  column "reverseDocumentId" {
    null = false
    type = uuid
  }
  column "createdAt" {
    null = false
    type = timestamptz
  }
  column "updatedAt" {
    null = false
    type = timestamptz
  }
  column "type" {
    null    = false
    type    = enum.enum_relationships_type
    default = "backlink"
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "backlinks_documentId_fkey" {
    columns     = [column.documentId]
    ref_columns = [table.documents.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "backlinks_reverseDocumentId_fkey" {
    columns     = [column.reverseDocumentId]
    ref_columns = [table.documents.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "backlinks_userId_fkey" {
    columns     = [column.userId]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "backlinks_document_id" {
    columns = [column.documentId]
  }
  index "backlinks_reverse_document_id" {
    columns = [column.reverseDocumentId]
  }
  index "relationships_document_id_type" {
    columns = [column.documentId, column.type]
  }
}
table "revisions" {
  schema = schema.public
  column "id" {
    null = false
    type = uuid
  }
  column "title" {
    null = false
    type = character_varying
  }
  column "text" {
    null = true
    type = text
  }
  column "createdAt" {
    null = false
    type = timestamptz
  }
  column "updatedAt" {
    null = false
    type = timestamptz
  }
  column "userId" {
    null = false
    type = uuid
  }
  column "documentId" {
    null = false
    type = uuid
  }
  column "editorVersion" {
    null = true
    type = character_varying(255)
  }
  column "version" {
    null = true
    type = smallint
  }
  column "content" {
    null = true
    type = jsonb
  }
  column "icon" {
    null = true
    type = character_varying(255)
  }
  column "color" {
    null = true
    type = character_varying(255)
  }
  column "name" {
    null = true
    type = character_varying(255)
  }
  column "deletedAt" {
    null = true
    type = timestamptz
  }
  column "collaboratorIds" {
    null    = false
    type    = sql("uuid[]")
    default = sql("ARRAY[]::uuid[]")
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "revisions_documentId_fkey" {
    columns     = [column.documentId]
    ref_columns = [table.documents.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "revisions_userId_fkey" {
    columns     = [column.userId]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "revisions_created_at" {
    columns = [column.createdAt]
  }
  index "revisions_document_id" {
    columns = [column.documentId]
  }
}
table "search_queries" {
  schema = schema.public
  column "id" {
    null = false
    type = uuid
  }
  column "userId" {
    null = true
    type = uuid
  }
  column "teamId" {
    null = true
    type = uuid
  }
  column "source" {
    null = false
    type = enum.enum_search_queries_source
  }
  column "query" {
    null = false
    type = character_varying(255)
  }
  column "results" {
    null = false
    type = integer
  }
  column "createdAt" {
    null = false
    type = timestamptz
  }
  column "shareId" {
    null = true
    type = uuid
  }
  column "score" {
    null = true
    type = integer
  }
  column "answer" {
    null = true
    type = text
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "search_queries_shareId_fkey" {
    columns     = [column.shareId]
    ref_columns = [table.shares.column.id]
    on_update   = NO_ACTION
    on_delete   = SET_NULL
  }
  foreign_key "search_queries_teamId_fkey" {
    columns     = [column.teamId]
    ref_columns = [table.teams.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "search_queries_userId_fkey" {
    columns     = [column.userId]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "search_queries_created_at" {
    columns = [column.createdAt]
  }
  index "search_queries_team_id" {
    columns = [column.teamId]
  }
  index "search_queries_user_id" {
    columns = [column.userId]
  }
}
table "shares" {
  schema = schema.public
  column "id" {
    null = false
    type = uuid
  }
  column "userId" {
    null = false
    type = uuid
  }
  column "teamId" {
    null = false
    type = uuid
  }
  column "documentId" {
    null = true
    type = uuid
  }
  column "createdAt" {
    null = false
    type = timestamptz
  }
  column "updatedAt" {
    null = false
    type = timestamptz
  }
  column "revokedAt" {
    null = true
    type = timestamptz
  }
  column "revokedById" {
    null = true
    type = uuid
  }
  column "published" {
    null    = false
    type    = boolean
    default = false
  }
  column "lastAccessedAt" {
    null = true
    type = timestamptz
  }
  column "includeChildDocuments" {
    null    = false
    type    = boolean
    default = false
  }
  column "views" {
    null    = true
    type    = integer
    default = 0
  }
  column "urlId" {
    null = true
    type = character_varying(255)
  }
  column "domain" {
    null = true
    type = character_varying(255)
  }
  column "allowIndexing" {
    null    = false
    type    = boolean
    default = true
  }
  column "showLastUpdated" {
    null    = false
    type    = boolean
    default = false
  }
  column "collectionId" {
    null = true
    type = uuid
  }
  column "showTOC" {
    null    = false
    type    = boolean
    default = false
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "shares_collectionId_fkey" {
    columns     = [column.collectionId]
    ref_columns = [table.collections.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "shares_documentId_fkey" {
    columns     = [column.documentId]
    ref_columns = [table.documents.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "shares_revokedById_fkey" {
    columns     = [column.revokedById]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "shares_teamId_fkey" {
    columns     = [column.teamId]
    ref_columns = [table.teams.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "shares_userId_fkey" {
    columns     = [column.userId]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "shares_urlId_teamId_not_revoked_uk" {
    unique  = true
    columns = [column.urlId, column.teamId]
    where   = "(\"revokedAt\" IS NULL)"
  }
  unique "shares_domain_key" {
    columns = [column.domain]
  }
}
table "stars" {
  schema = schema.public
  column "id" {
    null = false
    type = uuid
  }
  column "documentId" {
    null = true
    type = uuid
  }
  column "userId" {
    null = false
    type = uuid
  }
  column "createdAt" {
    null = false
    type = timestamptz
  }
  column "updatedAt" {
    null = false
    type = timestamptz
  }
  column "index" {
    null = true
    type = character_varying(255)
  }
  column "collectionId" {
    null = true
    type = uuid
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "stars_collectionId_fkey" {
    columns     = [column.collectionId]
    ref_columns = [table.collections.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "stars_documentId_fkey" {
    columns     = [column.documentId]
    ref_columns = [table.documents.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "stars_userId_fkey" {
    columns     = [column.userId]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  index "stars_document_id_user_id" {
    columns = [column.documentId, column.userId]
  }
  index "stars_user_id_document_id" {
    columns = [column.userId, column.documentId]
  }
}
table "subscriptions" {
  schema = schema.public
  column "id" {
    null = false
    type = uuid
  }
  column "userId" {
    null = false
    type = uuid
  }
  column "documentId" {
    null = true
    type = uuid
  }
  column "event" {
    null = false
    type = character_varying(255)
  }
  column "createdAt" {
    null = false
    type = timestamptz
  }
  column "updatedAt" {
    null = false
    type = timestamptz
  }
  column "deletedAt" {
    null = true
    type = timestamptz
  }
  column "collectionId" {
    null = true
    type = uuid
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "subscriptions_collectionId_fkey" {
    columns     = [column.collectionId]
    ref_columns = [table.collections.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "subscriptions_documentId_fkey" {
    columns     = [column.documentId]
    ref_columns = [table.documents.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "subscriptions_userId_fkey" {
    columns     = [column.userId]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  index "subscriptions_event_collection_id" {
    columns = [column.event, column.collectionId]
    where   = "(\"deletedAt\" IS NULL)"
  }
  index "subscriptions_event_document_id" {
    columns = [column.event, column.documentId]
    where   = "(\"deletedAt\" IS NULL)"
  }
  index "subscriptions_user_id_collection_id_event" {
    unique  = true
    columns = [column.userId, column.collectionId, column.event]
  }
  index "subscriptions_user_id_document_id_event" {
    unique  = true
    columns = [column.userId, column.documentId, column.event]
  }
}
table "team_domains" {
  schema = schema.public
  column "id" {
    null = false
    type = uuid
  }
  column "teamId" {
    null = false
    type = uuid
  }
  column "createdById" {
    null = false
    type = uuid
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "createdAt" {
    null = false
    type = timestamptz
  }
  column "updatedAt" {
    null = false
    type = timestamptz
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "team_domains_createdById_fkey" {
    columns     = [column.createdById]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = SET_NULL
  }
  foreign_key "team_domains_teamId_fkey" {
    columns     = [column.teamId]
    ref_columns = [table.teams.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  index "team_domains_team_id_name" {
    unique  = true
    columns = [column.teamId, column.name]
  }
}
table "teams" {
  schema = schema.public
  column "id" {
    null = false
    type = uuid
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "createdAt" {
    null = false
    type = timestamptz
  }
  column "updatedAt" {
    null = false
    type = timestamptz
  }
  column "avatarUrl" {
    null = true
    type = character_varying(4096)
  }
  column "deletedAt" {
    null = true
    type = timestamptz
  }
  column "sharing" {
    null    = false
    type    = boolean
    default = true
  }
  column "subdomain" {
    null = true
    type = character_varying(255)
  }
  column "documentEmbeds" {
    null    = false
    type    = boolean
    default = true
  }
  column "guestSignin" {
    null    = false
    type    = boolean
    default = false
  }
  column "domain" {
    null = true
    type = character_varying(255)
  }
  column "signupQueryParams" {
    null = true
    type = jsonb
  }
  column "collaborativeEditing" {
    null = true
    type = boolean
  }
  column "defaultUserRole" {
    null    = false
    type    = character_varying(255)
    default = "member"
  }
  column "defaultCollectionId" {
    null = true
    type = uuid
  }
  column "memberCollectionCreate" {
    null    = false
    type    = boolean
    default = true
  }
  column "inviteRequired" {
    null    = false
    type    = boolean
    default = false
  }
  column "preferences" {
    null = true
    type = jsonb
  }
  column "suspendedAt" {
    null = true
    type = timestamptz
  }
  column "lastActiveAt" {
    null = true
    type = timestamptz
  }
  column "memberTeamCreate" {
    null    = false
    type    = boolean
    default = true
  }
  column "approximateTotalAttachmentsSize" {
    null    = true
    type    = bigint
    default = 0
  }
  column "previousSubdomains" {
    null = true
    type = sql("character varying(255)[]")
  }
  column "description" {
    null = true
    type = text
  }
  column "passkeysEnabled" {
    null    = false
    type    = boolean
    default = false
  }
  column "flags" {
    null = true
    type = jsonb
  }
  primary_key {
    columns = [column.id]
  }
  index "teams_previous_subdomains" {
    columns = [column.previousSubdomains]
    type    = GIN
  }
  index "teams_subdomain" {
    columns = [column.subdomain]
  }
  unique "teams_domain_key" {
    columns = [column.domain]
  }
  unique "teams_subdomain_key" {
    columns = [column.subdomain]
  }
}
table "user_authentications" {
  schema = schema.public
  column "id" {
    null = false
    type = uuid
  }
  column "userId" {
    null = false
    type = uuid
  }
  column "authenticationProviderId" {
    null = false
    type = uuid
  }
  column "accessToken" {
    null = true
    type = bytea
  }
  column "refreshToken" {
    null = true
    type = bytea
  }
  column "scopes" {
    null = true
    type = sql("character varying(255)[]")
  }
  column "providerId" {
    null = false
    type = character_varying(255)
  }
  column "createdAt" {
    null = false
    type = timestamptz
  }
  column "updatedAt" {
    null = false
    type = timestamptz
  }
  column "expiresAt" {
    null = true
    type = timestamptz
  }
  column "lastValidatedAt" {
    null = true
    type = timestamptz
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "user_authentications_authenticationProviderId_fkey" {
    columns     = [column.authenticationProviderId]
    ref_columns = [table.authentication_providers.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "user_authentications_userId_fkey" {
    columns     = [column.userId]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  index "user_authentications_providerId_createdAt" {
    columns = [column.providerId, column.createdAt]
  }
  index "user_authentications_user_id" {
    columns = [column.userId]
  }
  unique "user_authentications_providerId_userId_uk" {
    columns = [column.providerId, column.userId]
  }
}
table "user_passkeys" {
  schema = schema.public
  column "id" {
    null = false
    type = uuid
  }
  column "name" {
    null = false
    type = text
  }
  column "userAgent" {
    null = true
    type = text
  }
  column "credentialId" {
    null = false
    type = text
  }
  column "credentialPublicKey" {
    null = false
    type = bytea
  }
  column "aaguid" {
    null = true
    type = text
  }
  column "counter" {
    null    = false
    type    = bigint
    default = 0
  }
  column "transports" {
    null = true
    type = sql("character varying(255)[]")
  }
  column "lastActiveAt" {
    null = true
    type = timestamptz
  }
  column "userId" {
    null = false
    type = uuid
  }
  column "createdAt" {
    null = false
    type = timestamptz
  }
  column "updatedAt" {
    null = false
    type = timestamptz
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "user_passkeys_userId_fkey" {
    columns     = [column.userId]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  index "user_passkeys_user_id" {
    columns = [column.userId]
  }
  unique "user_passkeys_credentialId_key" {
    columns = [column.credentialId]
  }
}
table "user_permissions" {
  schema = schema.public
  column "collectionId" {
    null = true
    type = uuid
  }
  column "userId" {
    null = false
    type = uuid
  }
  column "permission" {
    null    = false
    type    = character_varying(255)
    default = "read_write"
  }
  column "createdById" {
    null = false
    type = uuid
  }
  column "createdAt" {
    null = false
    type = timestamptz
  }
  column "updatedAt" {
    null = false
    type = timestamptz
  }
  column "documentId" {
    null = true
    type = uuid
  }
  column "index" {
    null = true
    type = character_varying(255)
  }
  column "id" {
    null    = false
    type    = uuid
    default = sql("public.uuid_generate_v4()")
  }
  column "sourceId" {
    null = true
    type = uuid
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "user_permissions_collectionId_fkey" {
    columns     = [column.collectionId]
    ref_columns = [table.collections.column.id]
    on_update   = NO_ACTION
    on_delete   = SET_NULL
  }
  foreign_key "user_permissions_createdById_fkey" {
    columns     = [column.createdById]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "user_permissions_documentId_fkey" {
    columns     = [column.documentId]
    ref_columns = [table.documents.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "user_permissions_sourceId_fkey" {
    columns     = [column.sourceId]
    ref_columns = [table.user_permissions.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "user_permissions_userId_fkey" {
    columns     = [column.userId]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  index "user_permissions_collection_id_user_id" {
    columns = [column.collectionId, column.userId]
  }
  index "user_permissions_document_id_user_id" {
    columns = [column.documentId, column.userId]
  }
  index "user_permissions_source_id" {
    columns = [column.sourceId]
  }
  index "user_permissions_user_id" {
    columns = [column.userId]
  }
}
table "users" {
  schema = schema.public
  column "id" {
    null = false
    type = uuid
  }
  column "email" {
    null    = true
    type    = character_varying(255)
    default = sql("NULL::character varying")
  }
  column "name" {
    null = false
    type = character_varying
  }
  column "jwtSecret" {
    null = true
    type = bytea
  }
  column "createdAt" {
    null = false
    type = timestamptz
  }
  column "updatedAt" {
    null = false
    type = timestamptz
  }
  column "teamId" {
    null = true
    type = uuid
  }
  column "avatarUrl" {
    null = true
    type = character_varying(4096)
  }
  column "suspendedById" {
    null = true
    type = uuid
  }
  column "suspendedAt" {
    null = true
    type = timestamptz
  }
  column "lastActiveAt" {
    null = true
    type = timestamptz
  }
  column "lastActiveIp" {
    null = true
    type = character_varying(255)
  }
  column "lastSignedInAt" {
    null = true
    type = timestamptz
  }
  column "lastSignedInIp" {
    null = true
    type = character_varying(255)
  }
  column "deletedAt" {
    null = true
    type = timestamptz
  }
  column "lastSigninEmailSentAt" {
    null = true
    type = timestamptz
  }
  column "language" {
    null = true
    type = character_varying(255)
  }
  column "flags" {
    null = true
    type = jsonb
  }
  column "invitedById" {
    null = true
    type = uuid
  }
  column "preferences" {
    null = true
    type = jsonb
  }
  column "notificationSettings" {
    null    = false
    type    = jsonb
    default = "{}"
  }
  column "role" {
    null = false
    type = enum.enum_users_role
  }
  column "timezone" {
    null = true
    type = character_varying(255)
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "users_invitedById_fkey" {
    columns     = [column.invitedById]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "users_suspendedById_fkey" {
    columns     = [column.suspendedById]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  foreign_key "users_teamId_fkey" {
    columns     = [column.teamId]
    ref_columns = [table.teams.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  index "users_email" {
    columns = [column.email]
  }
  index "users_team_id" {
    columns = [column.teamId]
  }
}
table "views" {
  schema = schema.public
  column "id" {
    null = false
    type = uuid
  }
  column "documentId" {
    null = false
    type = uuid
  }
  column "userId" {
    null = false
    type = uuid
  }
  column "count" {
    null    = false
    type    = integer
    default = 1
  }
  column "createdAt" {
    null = false
    type = timestamptz
  }
  column "updatedAt" {
    null = false
    type = timestamptz
  }
  column "lastEditingAt" {
    null = true
    type = timestamptz
  }
  primary_key {
    columns = [column.id]
  }
  index "views_document_id_user_id" {
    columns = [column.documentId, column.userId]
  }
  index "views_updated_at" {
    columns = [column.updatedAt]
  }
  index "views_user_id" {
    columns = [column.userId]
  }
}
table "webhook_deliveries" {
  schema = schema.public
  column "id" {
    null = false
    type = uuid
  }
  column "webhookSubscriptionId" {
    null = false
    type = uuid
  }
  column "status" {
    null = false
    type = character_varying(255)
  }
  column "statusCode" {
    null = true
    type = integer
  }
  column "requestBody" {
    null = true
    type = jsonb
  }
  column "requestHeaders" {
    null = true
    type = jsonb
  }
  column "responseBody" {
    null = true
    type = text
  }
  column "responseHeaders" {
    null = true
    type = jsonb
  }
  column "createdAt" {
    null = false
    type = timestamptz
  }
  column "updatedAt" {
    null = false
    type = timestamptz
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "webhook_deliveries_webhookSubscriptionId_fkey" {
    columns     = [column.webhookSubscriptionId]
    ref_columns = [table.webhook_subscriptions.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  index "webhook_deliveries_createdAt" {
    columns = [column.createdAt]
  }
  index "webhook_deliveries_webhook_subscription_id" {
    columns = [column.webhookSubscriptionId]
  }
}
table "webhook_subscriptions" {
  schema = schema.public
  column "id" {
    null = false
    type = uuid
  }
  column "teamId" {
    null = false
    type = uuid
  }
  column "createdById" {
    null = false
    type = uuid
  }
  column "url" {
    null = false
    type = character_varying(255)
  }
  column "enabled" {
    null = false
    type = boolean
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "events" {
    null = false
    type = sql("character varying(255)[]")
  }
  column "createdAt" {
    null = false
    type = timestamptz
  }
  column "updatedAt" {
    null = false
    type = timestamptz
  }
  column "deletedAt" {
    null = true
    type = timestamptz
  }
  column "secret" {
    null = true
    type = bytea
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "webhook_subscriptions_createdById_fkey" {
    columns     = [column.createdById]
    ref_columns = [table.users.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "webhook_subscriptions_teamId_fkey" {
    columns     = [column.teamId]
    ref_columns = [table.teams.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  index "webhook_subscriptions_team_id_enabled" {
    columns = [column.teamId, column.enabled]
  }
}
enum "enum_search_queries_source" {
  schema = schema.public
  values = ["slack", "app", "api", "oauth"]
}
enum "enum_file_operations_state" {
  schema = schema.public
  values = ["creating", "uploading", "complete", "error", "expired"]
}
enum "enum_file_operations_type" {
  schema = schema.public
  values = ["import", "export"]
}
enum "enum_users_role" {
  schema = schema.public
  values = ["admin", "member", "viewer", "guest"]
}
enum "enum_relationships_type" {
  schema = schema.public
  values = ["backlink", "similar"]
}
enum "enum_group_users_permission" {
  schema = schema.public
  values = ["admin", "member"]
}
schema "public" {
  comment = "standard public schema"
}
