// Telegram command bot for Huly Tracker.
// /tasks            -> lists the 10 most recently updated issues in the project
// /add <text>       -> creates a new issue titled <text>
// Anything else     -> short help message
//
// Uses its OWN Telegram bot (separate from huly-telegram-1's MTProto sync
// bot) so long-polling here never competes for updates. Restricted to a
// single allow-listed Telegram user id.
'use strict'

const { connect, NodeWebSocketFactory } = require('@hcengineering/api-client')
// These packages' CJS builds put namespace objects (space, class, taskTypes)
// under .default while some named exports (generateId, IssuePriority) stay
// top-level — merge both so either access pattern works.
const mergeDefault = (mod) => ({ ...(mod.default ?? {}), ...mod })
const core = mergeDefault(require('@hcengineering/core'))
const { generateId, SortingOrder } = core
const { makeRank } = require('@hcengineering/rank')
const tracker = mergeDefault(require('@hcengineering/tracker'))
const { IssuePriority } = tracker

const HULY_URL = required('HULY_URL')
const HULY_TOKEN = required('HULY_TOKEN')
const HULY_WORKSPACE = required('HULY_WORKSPACE')
const HULY_PROJECT_IDENTIFIER = required('HULY_PROJECT_IDENTIFIER')
const TELEGRAM_BOT_TOKEN = required('TELEGRAM_BOT_TOKEN')
const TELEGRAM_ALLOWED_USER_ID = required('TELEGRAM_ALLOWED_USER_ID')

function required (name) {
  const v = process.env[name]
  if (!v) {
    console.error(`missing required env var: ${name}`)
    process.exit(1)
  }
  return v
}

const TG_API = `https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}`

async function tgCall (method, body) {
  const res = await fetch(`${TG_API}/${method}`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body)
  })
  const data = await res.json()
  if (!data.ok) {
    console.error(`telegram ${method} failed:`, data)
  }
  return data
}

function sendMessage (chatId, text) {
  return tgCall('sendMessage', { chat_id: chatId, text, disable_web_page_preview: true })
}

let hulyClient

async function getHulyClient () {
  if (hulyClient !== undefined) return hulyClient
  hulyClient = await connect(HULY_URL, {
    token: HULY_TOKEN,
    workspace: HULY_WORKSPACE,
    socketFactory: NodeWebSocketFactory,
    connectionTimeout: 30000
  })
  return hulyClient
}

async function listRecentIssues () {
  const client = await getHulyClient()
  const project = await client.findOne(tracker.class.Project, { identifier: HULY_PROJECT_IDENTIFIER })
  if (project === undefined) throw new Error(`project ${HULY_PROJECT_IDENTIFIER} not found`)

  const issues = await client.findAll(
    tracker.class.Issue,
    { space: project._id },
    { limit: 10, sort: { modifiedOn: SortingOrder.Descending } }
  )
  if (issues.length === 0) return 'No issues yet.'

  const lines = await Promise.all(issues.map(async (issue) => {
    const status = await client.findOne(tracker.class.IssueStatus, { _id: issue.status })
    return `${issue.identifier}  [${status?.name ?? 'unknown'}]  ${issue.title}`
  }))
  return lines.join('\n')
}

async function createIssue (title) {
  const client = await getHulyClient()
  const project = await client.findOne(tracker.class.Project, { identifier: HULY_PROJECT_IDENTIFIER })
  if (project === undefined) throw new Error(`project ${HULY_PROJECT_IDENTIFIER} not found`)

  const issueId = generateId()
  const inc = await client.updateDoc(
    tracker.class.Project, core.space.Space, project._id, { $inc: { sequence: 1 } }, true
  )
  const sequence = inc.object.sequence

  const lastOne = await client.findOne(
    tracker.class.Issue, { space: project._id }, { sort: { rank: SortingOrder.Descending } }
  )

  const description = await client.uploadMarkup(tracker.class.Issue, issueId, 'description', '', 'markdown')

  await client.addCollection(
    tracker.class.Issue, project._id, project._id, project._class, 'issues',
    {
      title,
      description,
      status: project.defaultIssueStatus,
      number: sequence,
      kind: tracker.taskTypes.Issue,
      identifier: `${project.identifier}-${sequence}`,
      priority: IssuePriority.NoPriority,
      assignee: null,
      component: null,
      estimation: 0,
      remainingTime: 0,
      reportedTime: 0,
      reports: 0,
      subIssues: 0,
      parents: [],
      childInfo: [],
      dueDate: null,
      rank: makeRank(lastOne?.rank, undefined)
    },
    issueId
  )
  return `${project.identifier}-${sequence}`
}

const HELP_TEXT = [
  '/tasks - list the 10 most recently updated issues',
  '/add <text> - create a new issue titled <text>'
].join('\n')

async function handleMessage (message) {
  const chatId = message.chat.id
  const userId = message.from?.id
  if (String(userId) !== String(TELEGRAM_ALLOWED_USER_ID)) {
    console.warn(`ignoring message from unauthorized user id ${userId}`)
    return
  }

  const text = (message.text ?? '').trim()

  if (text === '/start' || text === '/help') {
    await sendMessage(chatId, HELP_TEXT)
    return
  }

  if (text === '/tasks') {
    try {
      const listing = await listRecentIssues()
      await sendMessage(chatId, listing)
    } catch (err) {
      console.error(err)
      await sendMessage(chatId, `failed to list issues: ${err.message}`)
    }
    return
  }

  if (text.startsWith('/add ')) {
    const title = text.slice('/add '.length).trim()
    if (title.length === 0) {
      await sendMessage(chatId, 'usage: /add <task title>')
      return
    }
    try {
      const identifier = await createIssue(title)
      await sendMessage(chatId, `created ${identifier}: ${title}`)
    } catch (err) {
      console.error(err)
      await sendMessage(chatId, `failed to create issue: ${err.message}`)
    }
    return
  }

  await sendMessage(chatId, HELP_TEXT)
}

async function pollLoop () {
  let offset = 0
  console.log('huly-task-bot: starting long poll')
  while (true) {
    let updates
    try {
      const res = await tgCall('getUpdates', { offset, timeout: 30 })
      updates = res.result ?? []
    } catch (err) {
      console.error('getUpdates failed:', err)
      await new Promise((r) => setTimeout(r, 5000))
      continue
    }
    for (const update of updates) {
      offset = update.update_id + 1
      if (update.message !== undefined) {
        await handleMessage(update.message).catch((err) => console.error('handleMessage error:', err))
      }
    }
  }
}

pollLoop().catch((err) => {
  console.error('fatal:', err)
  process.exit(1)
})
