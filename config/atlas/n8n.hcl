Notice: This Atlas edition lacks support for features such as checkpoints,
testing, down migrations, and more. Additionally, advanced database objects such as views,
triggers, and stored procedures are not supported. To read more: https://atlasgo.io/community-edition

To install the non-community version of Atlas, use the following command:

	curl -sSf https://atlasgo.sh | sh

Or, visit the website to see all installation options:

	https://atlasgo.io/docs#installation

table "annotation_tag_entity" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(16)
  }
  column "name" {
    null = false
    type = character_varying(24)
  }
  column "createdAt" {
    null    = false
    type    = timestamptz(3)
    default = sql("CURRENT_TIMESTAMP(3)")
  }
  column "updatedAt" {
    null    = false
    type    = timestamptz(3)
    default = sql("CURRENT_TIMESTAMP(3)")
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_ae51b54c4bb430cf92f48b623f" {
    unique  = true
    columns = [column.name]
  }
}
table "auth_identity" {
  schema = schema.public
  column "userId" {
    null = true
    type = uuid
  }
  column "providerId" {
    null = false
    type = character_varying(64)
  }
  column "providerType" {
    null = false
    type = character_varying(32)
  }
  column "createdAt" {
    null    = false
    type    = timestamptz(3)
    default = sql("CURRENT_TIMESTAMP(3)")
  }
  column "updatedAt" {
    null    = false
    type    = timestamptz(3)
    default = sql("CURRENT_TIMESTAMP(3)")
  }
  primary_key {
    columns = [column.providerId, column.providerType]
  }
  foreign_key "auth_identity_userId_fkey" {
    columns     = [column.userId]
    ref_columns = [table.user.column.id]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
}
table "auth_provider_sync_history" {
  schema = schema.public
  column "id" {
    null = false
    type = serial
  }
  column "providerType" {
    null = false
    type = character_varying(32)
  }
  column "runMode" {
    null = false
    type = text
  }
  column "status" {
    null = false
    type = text
  }
  column "startedAt" {
    null    = false
    type    = timestamptz(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "endedAt" {
    null    = false
    type    = timestamptz(3)
    default = sql("CURRENT_TIMESTAMP")
  }
  column "scanned" {
    null = false
    type = integer
  }
  column "created" {
    null = false
    type = integer
  }
  column "updated" {
    null = false
    type = integer
  }
  column "disabled" {
    null = false
    type = integer
  }
  column "error" {
    null = true
    type = text
  }
  primary_key {
    columns = [column.id]
  }
}
table "binary_data" {
  schema = schema.public
  column "fileId" {
    null = false
    type = uuid
  }
  column "sourceType" {
    null    = false
    type    = character_varying(50)
    comment = "Source the file belongs to, e.g. 'execution'"
  }
  column "sourceId" {
    null    = false
    type    = character_varying(255)
    comment = "ID of the source, e.g. execution ID"
  }
  column "data" {
    null    = false
    type    = bytea
    comment = "Raw, not base64 encoded"
  }
  column "mimeType" {
    null = true
    type = character_varying(255)
  }
  column "fileName" {
    null = true
    type = character_varying(255)
  }
  column "fileSize" {
    null    = false
    type    = integer
    comment = "In bytes"
  }
  column "createdAt" {
    null    = false
    type    = timestamptz(3)
    default = sql("CURRENT_TIMESTAMP(3)")
  }
  column "updatedAt" {
    null    = false
    type    = timestamptz(3)
    default = sql("CURRENT_TIMESTAMP(3)")
  }
  primary_key {
    columns = [column.fileId]
  }
  index "IDX_56900edc3cfd16612e2ef2c6a8" {
    columns = [column.sourceType, column.sourceId]
  }
  check "CHK_binary_data_sourceType" {
    expr = "((\"sourceType\")::text = ANY ((ARRAY['execution'::character varying, 'chat_message_attachment'::character varying])::text[]))"
  }
}
table "chat_hub_agents" {
  schema = schema.public
  column "id" {
    null = false
    type = uuid
  }
  column "name" {
    null = false
    type = character_varying(256)
  }
  column "description" {
    null = true
    type = character_varying(512)
  }
  column "systemPrompt" {
    null = false
    type = text
  }
  column "ownerId" {
    null = false
    type = uuid
  }
  column "credentialId" {
    null = true
    type = character_varying(36)
  }
  column "provider" {
    null    = false
    type    = character_varying(16)
    comment = "ChatHubProvider enum: \"openai\", \"anthropic\", \"google\", \"n8n\""
  }
  column "model" {
    null    = false
    type    = character_varying(64)
    comment = "Model name used at the respective Model node, ie. \"gpt-4\""
  }
  column "createdAt" {
    null    = false
    type    = timestamptz(3)
    default = sql("CURRENT_TIMESTAMP(3)")
  }
  column "updatedAt" {
    null    = false
    type    = timestamptz(3)
    default = sql("CURRENT_TIMESTAMP(3)")
  }
  column "tools" {
    null    = false
    type    = json
    default = "[]"
    comment = "Tools available to the agent as JSON node definitions"
  }
  column "icon" {
    null = true
    type = json
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "FK_441ba2caba11e077ce3fbfa2cd8" {
    columns     = [column.ownerId]
    ref_columns = [table.user.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "FK_9c61ad497dcbae499c96a6a78ba" {
    columns     = [column.credentialId]
    ref_columns = [table.credentials_entity.column.id]
    on_update   = NO_ACTION
    on_delete   = SET_NULL
  }
}
table "chat_hub_messages" {
  schema = schema.public
  column "id" {
    null = false
    type = uuid
  }
  column "sessionId" {
    null = false
    type = uuid
  }
  column "previousMessageId" {
    null = true
    type = uuid
  }
  column "revisionOfMessageId" {
    null = true
    type = uuid
  }
  column "retryOfMessageId" {
    null = true
    type = uuid
  }
  column "type" {
    null    = false
    type    = character_varying(16)
    comment = "ChatHubMessageType enum: \"human\", \"ai\", \"system\", \"tool\", \"generic\""
  }
  column "name" {
    null = false
    type = character_varying(128)
  }
  column "content" {
    null = false
    type = text
  }
  column "provider" {
    null    = true
    type    = character_varying(16)
    comment = "ChatHubProvider enum: \"openai\", \"anthropic\", \"google\", \"n8n\""
  }
  column "model" {
    null    = true
    type    = character_varying(64)
    comment = "Model name used at the respective Model node, ie. \"gpt-4\""
  }
  column "workflowId" {
    null = true
    type = character_varying(36)
  }
  column "executionId" {
    null = true
    type = integer
  }
  column "createdAt" {
    null    = false
    type    = timestamptz(3)
    default = sql("CURRENT_TIMESTAMP(3)")
  }
  column "updatedAt" {
    null    = false
    type    = timestamptz(3)
    default = sql("CURRENT_TIMESTAMP(3)")
  }
  column "agentId" {
    null    = true
    type    = uuid
    comment = "ID of the custom agent (if provider is \"custom-agent\")"
  }
  column "status" {
    null    = false
    type    = character_varying(16)
    default = "success"
    comment = "ChatHubMessageStatus enum, eg. \"success\", \"error\", \"running\", \"cancelled\""
  }
  column "attachments" {
    null    = true
    type    = json
    comment = "File attachments for the message (if any), stored as JSON. Files are stored as base64-encoded data URLs."
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "FK_1f4998c8a7dec9e00a9ab15550e" {
    columns     = [column.revisionOfMessageId]
    ref_columns = [table.chat_hub_messages.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "FK_25c9736e7f769f3a005eef4b372" {
    columns     = [column.retryOfMessageId]
    ref_columns = [table.chat_hub_messages.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "FK_6afb260449dd7a9b85355d4e0c9" {
    columns     = [column.executionId]
    ref_columns = [table.execution_entity.column.id]
    on_update   = NO_ACTION
    on_delete   = SET_NULL
  }
  foreign_key "FK_acf8926098f063cdbbad8497fd1" {
    columns     = [column.workflowId]
    ref_columns = [table.workflow_entity.column.id]
    on_update   = NO_ACTION
    on_delete   = SET_NULL
  }
  foreign_key "FK_chat_hub_messages_agentId" {
    columns     = [column.agentId]
    ref_columns = [table.chat_hub_agents.column.id]
    on_update   = NO_ACTION
    on_delete   = SET_NULL
  }
  foreign_key "FK_e22538eb50a71a17954cd7e076c" {
    columns     = [column.sessionId]
    ref_columns = [table.chat_hub_sessions.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "FK_e5d1fa722c5a8d38ac204746662" {
    columns     = [column.previousMessageId]
    ref_columns = [table.chat_hub_messages.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  index "IDX_chat_hub_messages_sessionId" {
    columns = [column.sessionId]
  }
}
table "chat_hub_sessions" {
  schema = schema.public
  column "id" {
    null = false
    type = uuid
  }
  column "title" {
    null = false
    type = character_varying(256)
  }
  column "ownerId" {
    null = false
    type = uuid
  }
  column "lastMessageAt" {
    null = false
    type = timestamptz(3)
  }
  column "credentialId" {
    null = true
    type = character_varying(36)
  }
  column "provider" {
    null    = true
    type    = character_varying(16)
    comment = "ChatHubProvider enum: \"openai\", \"anthropic\", \"google\", \"n8n\""
  }
  column "model" {
    null    = true
    type    = character_varying(64)
    comment = "Model name used at the respective Model node, ie. \"gpt-4\""
  }
  column "workflowId" {
    null = true
    type = character_varying(36)
  }
  column "createdAt" {
    null    = false
    type    = timestamptz(3)
    default = sql("CURRENT_TIMESTAMP(3)")
  }
  column "updatedAt" {
    null    = false
    type    = timestamptz(3)
    default = sql("CURRENT_TIMESTAMP(3)")
  }
  column "agentId" {
    null    = true
    type    = uuid
    comment = "ID of the custom agent (if provider is \"custom-agent\")"
  }
  column "agentName" {
    null    = true
    type    = character_varying(128)
    comment = "Cached name of the custom agent (if provider is \"custom-agent\")"
  }
  column "tools" {
    null    = false
    type    = json
    default = "[]"
    comment = "Tools available to the agent as JSON node definitions"
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "FK_7bc13b4c7e6afbfaf9be326c189" {
    columns     = [column.credentialId]
    ref_columns = [table.credentials_entity.column.id]
    on_update   = NO_ACTION
    on_delete   = SET_NULL
  }
  foreign_key "FK_9f9293d9f552496c40e0d1a8f80" {
    columns     = [column.workflowId]
    ref_columns = [table.workflow_entity.column.id]
    on_update   = NO_ACTION
    on_delete   = SET_NULL
  }
  foreign_key "FK_chat_hub_sessions_agentId" {
    columns     = [column.agentId]
    ref_columns = [table.chat_hub_agents.column.id]
    on_update   = NO_ACTION
    on_delete   = SET_NULL
  }
  foreign_key "FK_e9ecf8ede7d989fcd18790fe36a" {
    columns     = [column.ownerId]
    ref_columns = [table.user.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  index "IDX_chat_hub_sessions_owner_lastmsg_id" {
    on {
      column = column.ownerId
    }
    on {
      desc   = true
      column = column.lastMessageAt
    }
    on {
      column = column.id
    }
  }
}
table "credentials_entity" {
  schema = schema.public
  column "name" {
    null = false
    type = character_varying(128)
  }
  column "data" {
    null = false
    type = text
  }
  column "type" {
    null = false
    type = character_varying(128)
  }
  column "createdAt" {
    null    = false
    type    = timestamptz(3)
    default = sql("CURRENT_TIMESTAMP(3)")
  }
  column "updatedAt" {
    null    = false
    type    = timestamptz(3)
    default = sql("CURRENT_TIMESTAMP(3)")
  }
  column "id" {
    null = false
    type = character_varying(36)
  }
  column "isManaged" {
    null    = false
    type    = boolean
    default = false
  }
  column "isGlobal" {
    null    = false
    type    = boolean
    default = false
  }
  column "isResolvable" {
    null    = false
    type    = boolean
    default = false
  }
  column "resolvableAllowFallback" {
    null    = false
    type    = boolean
    default = false
  }
  column "resolverId" {
    null = true
    type = character_varying(16)
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "credentials_entity_resolverId_foreign" {
    columns     = [column.resolverId]
    ref_columns = [table.dynamic_credential_resolver.column.id]
    on_update   = NO_ACTION
    on_delete   = SET_NULL
  }
  index "idx_07fde106c0b471d8cc80a64fc8" {
    columns = [column.type]
  }
  index "pk_credentials_entity_id" {
    unique  = true
    columns = [column.id]
  }
}
table "data_table" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(36)
  }
  column "name" {
    null = false
    type = character_varying(128)
  }
  column "projectId" {
    null = false
    type = character_varying(36)
  }
  column "createdAt" {
    null    = false
    type    = timestamptz(3)
    default = sql("CURRENT_TIMESTAMP(3)")
  }
  column "updatedAt" {
    null    = false
    type    = timestamptz(3)
    default = sql("CURRENT_TIMESTAMP(3)")
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "FK_c2a794257dee48af7c9abf681de" {
    columns     = [column.projectId]
    ref_columns = [table.project.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  unique "UQ_b23096ef747281ac944d28e8b0d" {
    columns = [column.projectId, column.name]
  }
}
table "data_table_column" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(36)
  }
  column "name" {
    null = false
    type = character_varying(128)
  }
  column "type" {
    null    = false
    type    = character_varying(32)
    comment = "Expected: string, number, boolean, or date (not enforced as a constraint)"
  }
  column "index" {
    null    = false
    type    = integer
    comment = "Column order, starting from 0 (0 = first column)"
  }
  column "dataTableId" {
    null = false
    type = character_varying(36)
  }
  column "createdAt" {
    null    = false
    type    = timestamptz(3)
    default = sql("CURRENT_TIMESTAMP(3)")
  }
  column "updatedAt" {
    null    = false
    type    = timestamptz(3)
    default = sql("CURRENT_TIMESTAMP(3)")
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "FK_930b6e8faaf88294cef23484160" {
    columns     = [column.dataTableId]
    ref_columns = [table.data_table.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  unique "UQ_8082ec4890f892f0bc77473a123" {
    columns = [column.dataTableId, column.name]
  }
}
table "dynamic_credential_entry" {
  schema = schema.public
  column "credential_id" {
    null = false
    type = character_varying(16)
  }
  column "subject_id" {
    null = false
    type = character_varying(16)
  }
  column "resolver_id" {
    null = false
    type = character_varying(16)
  }
  column "data" {
    null = false
    type = text
  }
  column "createdAt" {
    null    = false
    type    = timestamptz(3)
    default = sql("CURRENT_TIMESTAMP(3)")
  }
  column "updatedAt" {
    null    = false
    type    = timestamptz(3)
    default = sql("CURRENT_TIMESTAMP(3)")
  }
  primary_key {
    columns = [column.credential_id, column.subject_id, column.resolver_id]
  }
  foreign_key "FK_d57808fe08b77464f6a88a25494" {
    columns     = [column.resolver_id]
    ref_columns = [table.dynamic_credential_resolver.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "FK_e97db563e505ae5f57ca33ef221" {
    columns     = [column.credential_id]
    ref_columns = [table.credentials_entity.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  index "IDX_99b3e329d13b7bb2fa9b6a43f5" {
    columns = [column.subject_id]
  }
  index "IDX_d57808fe08b77464f6a88a2549" {
    columns = [column.resolver_id]
  }
}
table "dynamic_credential_resolver" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(16)
  }
  column "name" {
    null = false
    type = character_varying(128)
  }
  column "type" {
    null = false
    type = character_varying(128)
  }
  column "config" {
    null    = false
    type    = text
    comment = "Encrypted resolver configuration (JSON encrypted as string)"
  }
  column "createdAt" {
    null    = false
    type    = timestamptz(3)
    default = sql("CURRENT_TIMESTAMP(3)")
  }
  column "updatedAt" {
    null    = false
    type    = timestamptz(3)
    default = sql("CURRENT_TIMESTAMP(3)")
  }
  primary_key {
    columns = [column.id]
  }
  index "IDX_9c9ee9df586e60bb723234e499" {
    columns = [column.type]
  }
}
table "event_destinations" {
  schema = schema.public
  column "id" {
    null = false
    type = uuid
  }
  column "destination" {
    null = false
    type = jsonb
  }
  column "createdAt" {
    null    = false
    type    = timestamptz(3)
    default = sql("CURRENT_TIMESTAMP(3)")
  }
  column "updatedAt" {
    null    = false
    type    = timestamptz(3)
    default = sql("CURRENT_TIMESTAMP(3)")
  }
  primary_key {
    columns = [column.id]
  }
}
table "execution_annotation_tags" {
  schema = schema.public
  column "annotationId" {
    null = false
    type = integer
  }
  column "tagId" {
    null = false
    type = character_varying(24)
  }
  primary_key {
    columns = [column.annotationId, column.tagId]
  }
  foreign_key "FK_a3697779b366e131b2bbdae2976" {
    columns     = [column.tagId]
    ref_columns = [table.annotation_tag_entity.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "FK_c1519757391996eb06064f0e7c8" {
    columns     = [column.annotationId]
    ref_columns = [table.execution_annotations.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  index "IDX_a3697779b366e131b2bbdae297" {
    columns = [column.tagId]
  }
  index "IDX_c1519757391996eb06064f0e7c" {
    columns = [column.annotationId]
  }
}
table "execution_annotations" {
  schema = schema.public
  column "id" {
    null = false
    type = serial
  }
  column "executionId" {
    null = false
    type = integer
  }
  column "vote" {
    null = true
    type = character_varying(6)
  }
  column "note" {
    null = true
    type = text
  }
  column "createdAt" {
    null    = false
    type    = timestamptz(3)
    default = sql("CURRENT_TIMESTAMP(3)")
  }
  column "updatedAt" {
    null    = false
    type    = timestamptz(3)
    default = sql("CURRENT_TIMESTAMP(3)")
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "FK_97f863fa83c4786f19565084960" {
    columns     = [column.executionId]
    ref_columns = [table.execution_entity.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  index "IDX_97f863fa83c4786f1956508496" {
    unique  = true
    columns = [column.executionId]
  }
}
table "execution_data" {
  schema = schema.public
  column "executionId" {
    null = false
    type = integer
  }
  column "workflowData" {
    null = false
    type = json
  }
  column "data" {
    null = false
    type = text
  }
  column "workflowVersionId" {
    null = true
    type = character_varying(36)
  }
  primary_key {
    columns = [column.executionId]
  }
  foreign_key "execution_data_fk" {
    columns     = [column.executionId]
    ref_columns = [table.execution_entity.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
}
table "execution_entity" {
  schema = schema.public
  column "id" {
    null = false
    type = serial
  }
  column "finished" {
    null = false
    type = boolean
  }
  column "mode" {
    null = false
    type = character_varying
  }
  column "retryOf" {
    null = true
    type = character_varying
  }
  column "retrySuccessId" {
    null = true
    type = character_varying
  }
  column "startedAt" {
    null = true
    type = timestamptz(3)
  }
  column "stoppedAt" {
    null = true
    type = timestamptz(3)
  }
  column "waitTill" {
    null = true
    type = timestamptz(3)
  }
  column "status" {
    null = false
    type = character_varying
  }
  column "workflowId" {
    null = false
    type = character_varying(36)
  }
  column "deletedAt" {
    null = true
    type = timestamptz(3)
  }
  column "createdAt" {
    null    = false
    type    = timestamptz(3)
    default = sql("CURRENT_TIMESTAMP(3)")
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "fk_execution_entity_workflow_id" {
    columns     = [column.workflowId]
    ref_columns = [table.workflow_entity.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  index "IDX_execution_entity_deletedAt" {
    columns = [column.deletedAt]
  }
  index "idx_execution_entity_stopped_at_status_deleted_at" {
    columns = [column.stoppedAt, column.status, column.deletedAt]
    where   = "((\"stoppedAt\" IS NOT NULL) AND (\"deletedAt\" IS NULL))"
  }
  index "idx_execution_entity_wait_till_status_deleted_at" {
    columns = [column.waitTill, column.status, column.deletedAt]
    where   = "((\"waitTill\" IS NOT NULL) AND (\"deletedAt\" IS NULL))"
  }
  index "idx_execution_entity_workflow_id_started_at" {
    columns = [column.workflowId, column.startedAt]
    where   = "((\"startedAt\" IS NOT NULL) AND (\"deletedAt\" IS NULL))"
  }
}
table "execution_metadata" {
  schema = schema.public
  column "id" {
    null = false
    type = serial
  }
  column "executionId" {
    null = false
    type = integer
  }
  column "key" {
    null = false
    type = character_varying(255)
  }
  column "value" {
    null = false
    type = text
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "FK_31d0b4c93fb85ced26f6005cda3" {
    columns     = [column.executionId]
    ref_columns = [table.execution_entity.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  index "IDX_cec8eea3bf49551482ccb4933e" {
    unique  = true
    columns = [column.executionId, column.key]
  }
}
table "folder" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(36)
  }
  column "name" {
    null = false
    type = character_varying(128)
  }
  column "parentFolderId" {
    null = true
    type = character_varying(36)
  }
  column "projectId" {
    null = false
    type = character_varying(36)
  }
  column "createdAt" {
    null    = false
    type    = timestamptz(3)
    default = sql("CURRENT_TIMESTAMP(3)")
  }
  column "updatedAt" {
    null    = false
    type    = timestamptz(3)
    default = sql("CURRENT_TIMESTAMP(3)")
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "FK_804ea52f6729e3940498bd54d78" {
    columns     = [column.parentFolderId]
    ref_columns = [table.folder.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "FK_a8260b0b36939c6247f385b8221" {
    columns     = [column.projectId]
    ref_columns = [table.project.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  index "IDX_14f68deffaf858465715995508" {
    unique  = true
    columns = [column.projectId, column.id]
  }
}
table "folder_tag" {
  schema = schema.public
  column "folderId" {
    null = false
    type = character_varying(36)
  }
  column "tagId" {
    null = false
    type = character_varying(36)
  }
  primary_key {
    columns = [column.folderId, column.tagId]
  }
  foreign_key "FK_94a60854e06f2897b2e0d39edba" {
    columns     = [column.folderId]
    ref_columns = [table.folder.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "FK_dc88164176283de80af47621746" {
    columns     = [column.tagId]
    ref_columns = [table.tag_entity.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
}
table "insights_by_period" {
  schema = schema.public
  column "id" {
    null = false
    type = integer
    identity {
      generated = BY_DEFAULT
    }
  }
  column "metaId" {
    null = false
    type = integer
  }
  column "type" {
    null    = false
    type    = integer
    comment = "0: time_saved_minutes, 1: runtime_milliseconds, 2: success, 3: failure"
  }
  column "value" {
    null = false
    type = bigint
  }
  column "periodUnit" {
    null    = false
    type    = integer
    comment = "0: hour, 1: day, 2: week"
  }
  column "periodStart" {
    null    = true
    type    = timestamptz(0)
    default = sql("CURRENT_TIMESTAMP")
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "FK_6414cfed98daabbfdd61a1cfbc0" {
    columns     = [column.metaId]
    ref_columns = [table.insights_metadata.column.metaId]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  index "IDX_60b6a84299eeb3f671dfec7693" {
    unique  = true
    columns = [column.periodStart, column.type, column.periodUnit, column.metaId]
  }
}
table "insights_metadata" {
  schema = schema.public
  column "metaId" {
    null = false
    type = integer
    identity {
      generated = BY_DEFAULT
    }
  }
  column "workflowId" {
    null = true
    type = character_varying(36)
  }
  column "projectId" {
    null = true
    type = character_varying(36)
  }
  column "workflowName" {
    null = false
    type = character_varying(128)
  }
  column "projectName" {
    null = false
    type = character_varying(255)
  }
  primary_key {
    columns = [column.metaId]
  }
  foreign_key "FK_1d8ab99d5861c9388d2dc1cf733" {
    columns     = [column.workflowId]
    ref_columns = [table.workflow_entity.column.id]
    on_update   = NO_ACTION
    on_delete   = SET_NULL
  }
  foreign_key "FK_2375a1eda085adb16b24615b69c" {
    columns     = [column.projectId]
    ref_columns = [table.project.column.id]
    on_update   = NO_ACTION
    on_delete   = SET_NULL
  }
  index "IDX_1d8ab99d5861c9388d2dc1cf73" {
    unique  = true
    columns = [column.workflowId]
  }
}
table "insights_raw" {
  schema = schema.public
  column "id" {
    null = false
    type = integer
    identity {
      generated = BY_DEFAULT
    }
  }
  column "metaId" {
    null = false
    type = integer
  }
  column "type" {
    null    = false
    type    = integer
    comment = "0: time_saved_minutes, 1: runtime_milliseconds, 2: success, 3: failure"
  }
  column "value" {
    null = false
    type = bigint
  }
  column "timestamp" {
    null    = false
    type    = timestamptz(0)
    default = sql("CURRENT_TIMESTAMP")
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "FK_6e2e33741adef2a7c5d66befa4e" {
    columns     = [column.metaId]
    ref_columns = [table.insights_metadata.column.metaId]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
}
table "installed_nodes" {
  schema = schema.public
  column "name" {
    null = false
    type = character_varying(200)
  }
  column "type" {
    null = false
    type = character_varying(200)
  }
  column "latestVersion" {
    null    = false
    type    = integer
    default = 1
  }
  column "package" {
    null = false
    type = character_varying(241)
  }
  primary_key {
    columns = [column.name]
  }
  foreign_key "FK_73f857fc5dce682cef8a99c11dbddbc969618951" {
    columns     = [column.package]
    ref_columns = [table.installed_packages.column.packageName]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
}
table "installed_packages" {
  schema = schema.public
  column "packageName" {
    null = false
    type = character_varying(214)
  }
  column "installedVersion" {
    null = false
    type = character_varying(50)
  }
  column "authorName" {
    null = true
    type = character_varying(70)
  }
  column "authorEmail" {
    null = true
    type = character_varying(70)
  }
  column "createdAt" {
    null    = false
    type    = timestamptz(3)
    default = sql("CURRENT_TIMESTAMP(3)")
  }
  column "updatedAt" {
    null    = false
    type    = timestamptz(3)
    default = sql("CURRENT_TIMESTAMP(3)")
  }
  primary_key {
    columns = [column.packageName]
  }
}
table "invalid_auth_token" {
  schema = schema.public
  column "token" {
    null = false
    type = character_varying(512)
  }
  column "expiresAt" {
    null = false
    type = timestamptz(3)
  }
  primary_key {
    columns = [column.token]
  }
}
table "migrations" {
  schema = schema.public
  column "id" {
    null = false
    type = serial
  }
  column "timestamp" {
    null = false
    type = bigint
  }
  column "name" {
    null = false
    type = character_varying
  }
  primary_key {
    columns = [column.id]
  }
}
table "oauth_access_tokens" {
  schema = schema.public
  column "token" {
    null = false
    type = character_varying
  }
  column "clientId" {
    null = false
    type = character_varying
  }
  column "userId" {
    null = false
    type = uuid
  }
  primary_key {
    columns = [column.token]
  }
  foreign_key "FK_7234a36d8e49a1fa85095328845" {
    columns     = [column.userId]
    ref_columns = [table.user.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "FK_78b26968132b7e5e45b75876481" {
    columns     = [column.clientId]
    ref_columns = [table.oauth_clients.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
}
table "oauth_authorization_codes" {
  schema = schema.public
  column "code" {
    null = false
    type = character_varying(255)
  }
  column "clientId" {
    null = false
    type = character_varying
  }
  column "userId" {
    null = false
    type = uuid
  }
  column "redirectUri" {
    null = false
    type = character_varying
  }
  column "codeChallenge" {
    null = false
    type = character_varying
  }
  column "codeChallengeMethod" {
    null = false
    type = character_varying(255)
  }
  column "expiresAt" {
    null    = false
    type    = bigint
    comment = "Unix timestamp in milliseconds"
  }
  column "state" {
    null = true
    type = character_varying
  }
  column "used" {
    null    = false
    type    = boolean
    default = false
  }
  column "createdAt" {
    null    = false
    type    = timestamptz(3)
    default = sql("CURRENT_TIMESTAMP(3)")
  }
  column "updatedAt" {
    null    = false
    type    = timestamptz(3)
    default = sql("CURRENT_TIMESTAMP(3)")
  }
  primary_key {
    columns = [column.code]
  }
  foreign_key "FK_64d965bd072ea24fb6da55468cd" {
    columns     = [column.clientId]
    ref_columns = [table.oauth_clients.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "FK_aa8d3560484944c19bdf79ffa16" {
    columns     = [column.userId]
    ref_columns = [table.user.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
}
table "oauth_clients" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "redirectUris" {
    null = false
    type = json
  }
  column "grantTypes" {
    null = false
    type = json
  }
  column "clientSecret" {
    null = true
    type = character_varying(255)
  }
  column "clientSecretExpiresAt" {
    null = true
    type = bigint
  }
  column "tokenEndpointAuthMethod" {
    null    = false
    type    = character_varying(255)
    default = "none"
    comment = "Possible values: none, client_secret_basic or client_secret_post"
  }
  column "createdAt" {
    null    = false
    type    = timestamptz(3)
    default = sql("CURRENT_TIMESTAMP(3)")
  }
  column "updatedAt" {
    null    = false
    type    = timestamptz(3)
    default = sql("CURRENT_TIMESTAMP(3)")
  }
  primary_key {
    columns = [column.id]
  }
}
table "oauth_refresh_tokens" {
  schema = schema.public
  column "token" {
    null = false
    type = character_varying(255)
  }
  column "clientId" {
    null = false
    type = character_varying
  }
  column "userId" {
    null = false
    type = uuid
  }
  column "expiresAt" {
    null    = false
    type    = bigint
    comment = "Unix timestamp in milliseconds"
  }
  column "createdAt" {
    null    = false
    type    = timestamptz(3)
    default = sql("CURRENT_TIMESTAMP(3)")
  }
  column "updatedAt" {
    null    = false
    type    = timestamptz(3)
    default = sql("CURRENT_TIMESTAMP(3)")
  }
  primary_key {
    columns = [column.token]
  }
  foreign_key "FK_a699f3ed9fd0c1b19bc2608ac53" {
    columns     = [column.userId]
    ref_columns = [table.user.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "FK_b388696ce4d8be7ffbe8d3e4b69" {
    columns     = [column.clientId]
    ref_columns = [table.oauth_clients.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
}
table "oauth_user_consents" {
  schema = schema.public
  column "id" {
    null = false
    type = integer
    identity {
      generated = BY_DEFAULT
    }
  }
  column "userId" {
    null = false
    type = uuid
  }
  column "clientId" {
    null = false
    type = character_varying
  }
  column "grantedAt" {
    null    = false
    type    = bigint
    comment = "Unix timestamp in milliseconds"
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "FK_21e6c3c2d78a097478fae6aaefa" {
    columns     = [column.userId]
    ref_columns = [table.user.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "FK_a651acea2f6c97f8c4514935486" {
    columns     = [column.clientId]
    ref_columns = [table.oauth_clients.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  unique "UQ_083721d99ce8db4033e2958ebb4" {
    columns = [column.userId, column.clientId]
  }
}
table "processed_data" {
  schema = schema.public
  column "workflowId" {
    null = false
    type = character_varying(36)
  }
  column "context" {
    null = false
    type = character_varying(255)
  }
  column "createdAt" {
    null    = false
    type    = timestamptz(3)
    default = sql("CURRENT_TIMESTAMP(3)")
  }
  column "updatedAt" {
    null    = false
    type    = timestamptz(3)
    default = sql("CURRENT_TIMESTAMP(3)")
  }
  column "value" {
    null = false
    type = text
  }
  primary_key {
    columns = [column.workflowId, column.context]
  }
  foreign_key "FK_06a69a7032c97a763c2c7599464" {
    columns     = [column.workflowId]
    ref_columns = [table.workflow_entity.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
}
table "project" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(36)
  }
  column "name" {
    null = false
    type = character_varying(255)
  }
  column "type" {
    null = false
    type = character_varying(36)
  }
  column "createdAt" {
    null    = false
    type    = timestamptz(3)
    default = sql("CURRENT_TIMESTAMP(3)")
  }
  column "updatedAt" {
    null    = false
    type    = timestamptz(3)
    default = sql("CURRENT_TIMESTAMP(3)")
  }
  column "icon" {
    null = true
    type = json
  }
  column "description" {
    null = true
    type = character_varying(512)
  }
  column "creatorId" {
    null    = true
    type    = uuid
    comment = "ID of the user who created the project"
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "projects_creatorId_foreign" {
    columns     = [column.creatorId]
    ref_columns = [table.user.column.id]
    on_update   = NO_ACTION
    on_delete   = SET_NULL
  }
}
table "project_relation" {
  schema = schema.public
  column "projectId" {
    null = false
    type = character_varying(36)
  }
  column "userId" {
    null = false
    type = uuid
  }
  column "role" {
    null = false
    type = character_varying
  }
  column "createdAt" {
    null    = false
    type    = timestamptz(3)
    default = sql("CURRENT_TIMESTAMP(3)")
  }
  column "updatedAt" {
    null    = false
    type    = timestamptz(3)
    default = sql("CURRENT_TIMESTAMP(3)")
  }
  primary_key {
    columns = [column.projectId, column.userId]
  }
  foreign_key "FK_5f0643f6717905a05164090dde7" {
    columns     = [column.userId]
    ref_columns = [table.user.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "FK_61448d56d61802b5dfde5cdb002" {
    columns     = [column.projectId]
    ref_columns = [table.project.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "FK_c6b99592dc96b0d836d7a21db91" {
    columns     = [column.role]
    ref_columns = [table.role.column.slug]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "IDX_5f0643f6717905a05164090dde" {
    columns = [column.userId]
  }
  index "IDX_61448d56d61802b5dfde5cdb00" {
    columns = [column.projectId]
  }
  index "project_relation_role_idx" {
    columns = [column.role]
  }
  index "project_relation_role_project_idx" {
    columns = [column.projectId, column.role]
  }
}
table "role" {
  schema = schema.public
  column "slug" {
    null    = false
    type    = character_varying(128)
    comment = "Unique identifier of the role for example: \"global:owner\""
  }
  column "displayName" {
    null    = true
    type    = text
    comment = "Name used to display in the UI"
  }
  column "description" {
    null    = true
    type    = text
    comment = "Text describing the scope in more detail of users"
  }
  column "roleType" {
    null    = true
    type    = text
    comment = "Type of the role, e.g., global, project, or workflow"
  }
  column "systemRole" {
    null    = false
    type    = boolean
    default = false
    comment = "Indicates if the role is managed by the system and cannot be edited"
  }
  column "createdAt" {
    null    = false
    type    = timestamptz(3)
    default = sql("CURRENT_TIMESTAMP(3)")
  }
  column "updatedAt" {
    null    = false
    type    = timestamptz(3)
    default = sql("CURRENT_TIMESTAMP(3)")
  }
  primary_key {
    columns = [column.slug]
  }
  index "IDX_UniqueRoleDisplayName" {
    unique  = true
    columns = [column.displayName]
  }
}
table "role_scope" {
  schema = schema.public
  column "roleSlug" {
    null = false
    type = character_varying(128)
  }
  column "scopeSlug" {
    null = false
    type = character_varying(128)
  }
  primary_key {
    columns = [column.roleSlug, column.scopeSlug]
  }
  foreign_key "FK_role" {
    columns     = [column.roleSlug]
    ref_columns = [table.role.column.slug]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  foreign_key "FK_scope" {
    columns     = [column.scopeSlug]
    ref_columns = [table.scope.column.slug]
    on_update   = CASCADE
    on_delete   = CASCADE
  }
  index "IDX_role_scope_scopeSlug" {
    columns = [column.scopeSlug]
  }
}
table "scope" {
  schema = schema.public
  column "slug" {
    null    = false
    type    = character_varying(128)
    comment = "Unique identifier of the scope for example: \"project:create\""
  }
  column "displayName" {
    null    = true
    type    = text
    comment = "Name used to display in the UI"
  }
  column "description" {
    null    = true
    type    = text
    comment = "Text describing the scope in more detail of users"
  }
  primary_key {
    columns = [column.slug]
  }
}
table "settings" {
  schema = schema.public
  column "key" {
    null = false
    type = character_varying(255)
  }
  column "value" {
    null = false
    type = text
  }
  column "loadOnStartup" {
    null    = false
    type    = boolean
    default = false
  }
  primary_key {
    columns = [column.key]
  }
}
table "shared_credentials" {
  schema = schema.public
  column "credentialsId" {
    null = false
    type = character_varying(36)
  }
  column "projectId" {
    null = false
    type = character_varying(36)
  }
  column "role" {
    null = false
    type = text
  }
  column "createdAt" {
    null    = false
    type    = timestamptz(3)
    default = sql("CURRENT_TIMESTAMP(3)")
  }
  column "updatedAt" {
    null    = false
    type    = timestamptz(3)
    default = sql("CURRENT_TIMESTAMP(3)")
  }
  primary_key {
    columns = [column.credentialsId, column.projectId]
  }
  foreign_key "FK_416f66fc846c7c442970c094ccf" {
    columns     = [column.credentialsId]
    ref_columns = [table.credentials_entity.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "FK_812c2852270da1247756e77f5a4" {
    columns     = [column.projectId]
    ref_columns = [table.project.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
}
table "shared_workflow" {
  schema = schema.public
  column "workflowId" {
    null = false
    type = character_varying(36)
  }
  column "projectId" {
    null = false
    type = character_varying(36)
  }
  column "role" {
    null = false
    type = text
  }
  column "createdAt" {
    null    = false
    type    = timestamptz(3)
    default = sql("CURRENT_TIMESTAMP(3)")
  }
  column "updatedAt" {
    null    = false
    type    = timestamptz(3)
    default = sql("CURRENT_TIMESTAMP(3)")
  }
  primary_key {
    columns = [column.workflowId, column.projectId]
  }
  foreign_key "FK_a45ea5f27bcfdc21af9b4188560" {
    columns     = [column.projectId]
    ref_columns = [table.project.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "FK_daa206a04983d47d0a9c34649ce" {
    columns     = [column.workflowId]
    ref_columns = [table.workflow_entity.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
}
table "tag_entity" {
  schema = schema.public
  column "name" {
    null = false
    type = character_varying(24)
  }
  column "createdAt" {
    null    = false
    type    = timestamptz(3)
    default = sql("CURRENT_TIMESTAMP(3)")
  }
  column "updatedAt" {
    null    = false
    type    = timestamptz(3)
    default = sql("CURRENT_TIMESTAMP(3)")
  }
  column "id" {
    null = false
    type = character_varying(36)
  }
  primary_key {
    columns = [column.id]
  }
  index "idx_812eb05f7451ca757fb98444ce" {
    unique  = true
    columns = [column.name]
  }
  index "pk_tag_entity_id" {
    unique  = true
    columns = [column.id]
  }
}
table "test_case_execution" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(36)
  }
  column "testRunId" {
    null = false
    type = character_varying(36)
  }
  column "executionId" {
    null = true
    type = integer
  }
  column "status" {
    null = false
    type = character_varying
  }
  column "runAt" {
    null = true
    type = timestamptz(3)
  }
  column "completedAt" {
    null = true
    type = timestamptz(3)
  }
  column "errorCode" {
    null = true
    type = character_varying
  }
  column "errorDetails" {
    null = true
    type = json
  }
  column "metrics" {
    null = true
    type = json
  }
  column "createdAt" {
    null    = false
    type    = timestamptz(3)
    default = sql("CURRENT_TIMESTAMP(3)")
  }
  column "updatedAt" {
    null    = false
    type    = timestamptz(3)
    default = sql("CURRENT_TIMESTAMP(3)")
  }
  column "inputs" {
    null = true
    type = json
  }
  column "outputs" {
    null = true
    type = json
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "FK_8e4b4774db42f1e6dda3452b2af" {
    columns     = [column.testRunId]
    ref_columns = [table.test_run.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "FK_e48965fac35d0f5b9e7f51d8c44" {
    columns     = [column.executionId]
    ref_columns = [table.execution_entity.column.id]
    on_update   = NO_ACTION
    on_delete   = SET_NULL
  }
  index "IDX_8e4b4774db42f1e6dda3452b2a" {
    columns = [column.testRunId]
  }
}
table "test_run" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(36)
  }
  column "workflowId" {
    null = false
    type = character_varying(36)
  }
  column "status" {
    null = false
    type = character_varying
  }
  column "errorCode" {
    null = true
    type = character_varying
  }
  column "errorDetails" {
    null = true
    type = json
  }
  column "runAt" {
    null = true
    type = timestamptz(3)
  }
  column "completedAt" {
    null = true
    type = timestamptz(3)
  }
  column "metrics" {
    null = true
    type = json
  }
  column "createdAt" {
    null    = false
    type    = timestamptz(3)
    default = sql("CURRENT_TIMESTAMP(3)")
  }
  column "updatedAt" {
    null    = false
    type    = timestamptz(3)
    default = sql("CURRENT_TIMESTAMP(3)")
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "FK_d6870d3b6e4c185d33926f423c8" {
    columns     = [column.workflowId]
    ref_columns = [table.workflow_entity.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  index "IDX_d6870d3b6e4c185d33926f423c" {
    columns = [column.workflowId]
  }
}
table "user" {
  schema = schema.public
  column "id" {
    null    = false
    type    = uuid
    default = sql("gen_random_uuid()")
  }
  column "email" {
    null = true
    type = character_varying(255)
  }
  column "firstName" {
    null = true
    type = character_varying(32)
  }
  column "lastName" {
    null = true
    type = character_varying(32)
  }
  column "password" {
    null = true
    type = character_varying(255)
  }
  column "personalizationAnswers" {
    null = true
    type = json
  }
  column "createdAt" {
    null    = false
    type    = timestamptz(3)
    default = sql("CURRENT_TIMESTAMP(3)")
  }
  column "updatedAt" {
    null    = false
    type    = timestamptz(3)
    default = sql("CURRENT_TIMESTAMP(3)")
  }
  column "settings" {
    null = true
    type = json
  }
  column "disabled" {
    null    = false
    type    = boolean
    default = false
  }
  column "mfaEnabled" {
    null    = false
    type    = boolean
    default = false
  }
  column "mfaSecret" {
    null = true
    type = text
  }
  column "mfaRecoveryCodes" {
    null = true
    type = text
  }
  column "lastActiveAt" {
    null = true
    type = date
  }
  column "roleSlug" {
    null    = false
    type    = character_varying(128)
    default = "global:member"
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "FK_eaea92ee7bfb9c1b6cd01505d56" {
    columns     = [column.roleSlug]
    ref_columns = [table.role.column.slug]
    on_update   = NO_ACTION
    on_delete   = NO_ACTION
  }
  index "user_role_idx" {
    columns = [column.roleSlug]
  }
  unique "UQ_e12875dfb3b1d92d7d7c5377e2" {
    columns = [column.email]
  }
}
table "user_api_keys" {
  schema = schema.public
  column "id" {
    null = false
    type = character_varying(36)
  }
  column "userId" {
    null = false
    type = uuid
  }
  column "label" {
    null = false
    type = character_varying(100)
  }
  column "apiKey" {
    null = false
    type = character_varying
  }
  column "createdAt" {
    null    = false
    type    = timestamptz(3)
    default = sql("CURRENT_TIMESTAMP(3)")
  }
  column "updatedAt" {
    null    = false
    type    = timestamptz(3)
    default = sql("CURRENT_TIMESTAMP(3)")
  }
  column "scopes" {
    null = true
    type = json
  }
  column "audience" {
    null    = false
    type    = character_varying
    default = "public-api"
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "FK_e131705cbbc8fb589889b02d457" {
    columns     = [column.userId]
    ref_columns = [table.user.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  index "IDX_1ef35bac35d20bdae979d917a3" {
    unique  = true
    columns = [column.apiKey]
  }
  index "IDX_63d7bbae72c767cf162d459fcc" {
    unique  = true
    columns = [column.userId, column.label]
  }
}
table "variables" {
  schema = schema.public
  column "key" {
    null = false
    type = character_varying(50)
  }
  column "type" {
    null    = false
    type    = character_varying(50)
    default = "string"
  }
  column "value" {
    null = true
    type = character_varying(255)
  }
  column "id" {
    null = false
    type = character_varying(36)
  }
  column "projectId" {
    null = true
    type = character_varying(36)
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "FK_42f6c766f9f9d2edcc15bdd6e9b" {
    columns     = [column.projectId]
    ref_columns = [table.project.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  index "variables_global_key_unique" {
    unique  = true
    columns = [column.key]
    where   = "(\"projectId\" IS NULL)"
  }
  index "variables_project_key_unique" {
    unique  = true
    columns = [column.projectId, column.key]
    where   = "(\"projectId\" IS NOT NULL)"
  }
}
table "webhook_entity" {
  schema = schema.public
  column "webhookPath" {
    null = false
    type = character_varying
  }
  column "method" {
    null = false
    type = character_varying
  }
  column "node" {
    null = false
    type = character_varying
  }
  column "webhookId" {
    null = true
    type = character_varying
  }
  column "pathLength" {
    null = true
    type = integer
  }
  column "workflowId" {
    null = false
    type = character_varying(36)
  }
  primary_key {
    columns = [column.webhookPath, column.method]
  }
  foreign_key "fk_webhook_entity_workflow_id" {
    columns     = [column.workflowId]
    ref_columns = [table.workflow_entity.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  index "idx_16f4436789e804e3e1c9eeb240" {
    columns = [column.webhookId, column.method, column.pathLength]
  }
}
table "workflow_dependency" {
  schema = schema.public
  column "id" {
    null = false
    type = integer
    identity {
      generated = BY_DEFAULT
    }
  }
  column "workflowId" {
    null = false
    type = character_varying(36)
  }
  column "workflowVersionId" {
    null    = false
    type    = integer
    comment = "Version of the workflow"
  }
  column "dependencyType" {
    null    = false
    type    = character_varying(32)
    comment = "Type of dependency: \"credential\", \"nodeType\", \"webhookPath\", or \"workflowCall\""
  }
  column "dependencyKey" {
    null    = false
    type    = character_varying(255)
    comment = "ID or name of the dependency"
  }
  column "dependencyInfo" {
    null    = true
    type    = json
    comment = "Additional info about the dependency, interpreted based on type"
  }
  column "indexVersionId" {
    null    = false
    type    = smallint
    default = 1
    comment = "Version of the index structure"
  }
  column "createdAt" {
    null    = false
    type    = timestamptz(3)
    default = sql("CURRENT_TIMESTAMP(3)")
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "FK_a4ff2d9b9628ea988fa9e7d0bf8" {
    columns     = [column.workflowId]
    ref_columns = [table.workflow_entity.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  index "IDX_a4ff2d9b9628ea988fa9e7d0bf" {
    columns = [column.workflowId]
  }
  index "IDX_e48a201071ab85d9d09119d640" {
    columns = [column.dependencyKey]
  }
  index "IDX_e7fe1cfda990c14a445937d0b9" {
    columns = [column.dependencyType]
  }
}
table "workflow_entity" {
  schema = schema.public
  column "name" {
    null = false
    type = character_varying(128)
  }
  column "active" {
    null = false
    type = boolean
  }
  column "nodes" {
    null = false
    type = json
  }
  column "connections" {
    null = false
    type = json
  }
  column "createdAt" {
    null    = false
    type    = timestamptz(3)
    default = sql("CURRENT_TIMESTAMP(3)")
  }
  column "updatedAt" {
    null    = false
    type    = timestamptz(3)
    default = sql("CURRENT_TIMESTAMP(3)")
  }
  column "settings" {
    null = true
    type = json
  }
  column "staticData" {
    null = true
    type = json
  }
  column "pinData" {
    null = true
    type = json
  }
  column "versionId" {
    null = false
    type = character(36)
  }
  column "triggerCount" {
    null    = false
    type    = integer
    default = 0
  }
  column "id" {
    null = false
    type = character_varying(36)
  }
  column "meta" {
    null = true
    type = json
  }
  column "parentFolderId" {
    null    = true
    type    = character_varying(36)
    default = sql("NULL::character varying")
  }
  column "isArchived" {
    null    = false
    type    = boolean
    default = false
  }
  column "versionCounter" {
    null    = false
    type    = integer
    default = 1
  }
  column "description" {
    null = true
    type = text
  }
  column "activeVersionId" {
    null = true
    type = character_varying(36)
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "FK_08d6c67b7f722b0039d9d5ed620" {
    columns     = [column.activeVersionId]
    ref_columns = [table.workflow_history.column.versionId]
    on_update   = NO_ACTION
    on_delete   = RESTRICT
  }
  foreign_key "fk_workflow_parent_folder" {
    columns     = [column.parentFolderId]
    ref_columns = [table.folder.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  index "IDX_workflow_entity_name" {
    columns = [column.name]
  }
  index "pk_workflow_entity_id" {
    unique  = true
    columns = [column.id]
  }
}
table "workflow_history" {
  schema = schema.public
  column "versionId" {
    null = false
    type = character_varying(36)
  }
  column "workflowId" {
    null = false
    type = character_varying(36)
  }
  column "authors" {
    null = false
    type = character_varying(255)
  }
  column "createdAt" {
    null    = false
    type    = timestamptz(3)
    default = sql("CURRENT_TIMESTAMP(3)")
  }
  column "updatedAt" {
    null    = false
    type    = timestamptz(3)
    default = sql("CURRENT_TIMESTAMP(3)")
  }
  column "nodes" {
    null = false
    type = json
  }
  column "connections" {
    null = false
    type = json
  }
  column "name" {
    null = true
    type = character_varying(128)
  }
  column "autosaved" {
    null    = false
    type    = boolean
    default = false
  }
  column "description" {
    null = true
    type = text
  }
  primary_key {
    columns = [column.versionId]
  }
  foreign_key "FK_1e31657f5fe46816c34be7c1b4b" {
    columns     = [column.workflowId]
    ref_columns = [table.workflow_entity.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  index "IDX_1e31657f5fe46816c34be7c1b4" {
    columns = [column.workflowId]
  }
}
table "workflow_publish_history" {
  schema = schema.public
  column "id" {
    null = false
    type = integer
    identity {
      generated = BY_DEFAULT
    }
  }
  column "workflowId" {
    null = false
    type = character_varying(36)
  }
  column "versionId" {
    null = false
    type = character_varying(36)
  }
  column "event" {
    null    = false
    type    = character_varying(36)
    comment = "Type of history record: activated (workflow is now active), deactivated (workflow is now inactive)"
  }
  column "userId" {
    null = true
    type = uuid
  }
  column "createdAt" {
    null    = false
    type    = timestamptz(3)
    default = sql("CURRENT_TIMESTAMP(3)")
  }
  primary_key {
    columns = [column.id]
  }
  foreign_key "FK_6eab5bd9eedabe9c54bd879fc40" {
    columns     = [column.userId]
    ref_columns = [table.user.column.id]
    on_update   = NO_ACTION
    on_delete   = SET_NULL
  }
  foreign_key "FK_b4cfbc7556d07f36ca177f5e473" {
    columns     = [column.versionId]
    ref_columns = [table.workflow_history.column.versionId]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "FK_c01316f8c2d7101ec4fa9809267" {
    columns     = [column.workflowId]
    ref_columns = [table.workflow_entity.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  index "IDX_070b5de842ece9ccdda0d9738b" {
    columns = [column.workflowId, column.versionId]
  }
  check "CHK_workflow_publish_history_event" {
    expr = "((event)::text = ANY ((ARRAY['activated'::character varying, 'deactivated'::character varying])::text[]))"
  }
}
table "workflow_statistics" {
  schema = schema.public
  column "count" {
    null    = true
    type    = integer
    default = 0
  }
  column "latestEvent" {
    null = true
    type = timestamptz(3)
  }
  column "name" {
    null = false
    type = character_varying(128)
  }
  column "workflowId" {
    null = false
    type = character_varying(36)
  }
  column "rootCount" {
    null    = true
    type    = integer
    default = 0
  }
  primary_key {
    columns = [column.workflowId, column.name]
  }
  foreign_key "fk_workflow_statistics_workflow_id" {
    columns     = [column.workflowId]
    ref_columns = [table.workflow_entity.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
}
table "workflows_tags" {
  schema = schema.public
  column "workflowId" {
    null = false
    type = character_varying(36)
  }
  column "tagId" {
    null = false
    type = character_varying(36)
  }
  primary_key {
    columns = [column.workflowId, column.tagId]
  }
  foreign_key "fk_workflows_tags_tag_id" {
    columns     = [column.tagId]
    ref_columns = [table.tag_entity.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  foreign_key "fk_workflows_tags_workflow_id" {
    columns     = [column.workflowId]
    ref_columns = [table.workflow_entity.column.id]
    on_update   = NO_ACTION
    on_delete   = CASCADE
  }
  index "idx_workflows_tags_workflow_id" {
    columns = [column.workflowId]
  }
}
schema "public" {
  comment = "standard public schema"
}
