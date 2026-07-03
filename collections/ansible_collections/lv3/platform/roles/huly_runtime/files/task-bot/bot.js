// Telegram command bot for Huly Tracker.
//
// /tasks              -> lists the 10 most recently updated issues
// /task <ID>          -> full details + quick-action buttons (Done, High
//                        priority, Delete) so common actions don't need typing
// /find <keyword>     -> search issue titles in the project
// /add <text>         -> creates a new issue, then follows up with an
//                        inline-keyboard category suggestion (tap one to
//                        file it under that component and prefix the title)
// /status <ID> <name> -> set status (backlog/todo/in progress/done/cancelled)
// /priority <ID> <name> -> set priority (urgent/high/medium/low/none)
// /assign <ID> <name> -> assign to a workspace member by name (substring match)
// /due <ID> <date>    -> set due date (today, tomorrow, or YYYY-MM-DD)
// /comment <ID> <text> -> add a comment without touching the title/description
// /delete <ID>        -> delete an issue
// Anything else       -> short help message
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
const contact = mergeDefault(require('@hcengineering/contact'))
const chunter = mergeDefault(require('@hcengineering/chunter'))

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

function sendMessage (chatId, text, extra) {
  return tgCall('sendMessage', { chat_id: chatId, text, disable_web_page_preview: true, ...extra })
}

function editMessageText (chatId, messageId, text, extra) {
  return tgCall('editMessageText', { chat_id: chatId, message_id: messageId, text, ...extra })
}

function answerCallbackQuery (id, text) {
  return tgCall('answerCallbackQuery', { callback_query_id: id, text })
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

async function getProject (client) {
  const project = await client.findOne(tracker.class.Project, { identifier: HULY_PROJECT_IDENTIFIER })
  if (project === undefined) throw new Error(`project ${HULY_PROJECT_IDENTIFIER} not found`)
  return project
}

async function findIssueByIdentifier (client, identifier) {
  const issue = await client.findOne(tracker.class.Issue, { identifier })
  if (issue === undefined) throw new Error(`issue ${identifier} not found`)
  return issue
}

function taskActionButtons (identifier) {
  return {
    reply_markup: {
      inline_keyboard: [[
        { text: 'Mark Done', callback_data: `done:${identifier}` },
        { text: 'High Priority', callback_data: `highpri:${identifier}` },
        { text: 'Delete', callback_data: `delask:${identifier}` }
      ]]
    }
  }
}

async function listRecentIssues () {
  const client = await getHulyClient()
  const project = await getProject(client)

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

async function findIssues (keyword) {
  const client = await getHulyClient()
  const project = await getProject(client)
  const issues = await client.findAll(tracker.class.Issue, { space: project._id })

  const needle = keyword.toLowerCase()
  const matches = issues.filter((i) => i.title.toLowerCase().includes(needle))
  if (matches.length === 0) return `No issues matching "${keyword}".`

  const lines = await Promise.all(matches.slice(0, 15).map(async (issue) => {
    const status = await client.findOne(tracker.class.IssueStatus, { _id: issue.status })
    return `${issue.identifier}  [${status?.name ?? 'unknown'}]  ${issue.title}`
  }))
  return lines.join('\n')
}

function formatDueDate (ts) {
  if (ts === null || ts === undefined) return '(none)'
  return new Date(ts).toISOString().slice(0, 10)
}

async function getIssueDetails (identifier) {
  const client = await getHulyClient()
  const issue = await findIssueByIdentifier(client, identifier)

  const status = await client.findOne(tracker.class.IssueStatus, { _id: issue.status })
  const priorityName = Object.entries(IssuePriority).find(([k, v]) => v === issue.priority && isNaN(Number(k)))?.[0]
  const component = issue.component !== null
    ? await client.findOne(tracker.class.Component, { _id: issue.component })
    : undefined
  const assignee = issue.assignee !== null
    ? await client.findOne(contact.class.Person, { _id: issue.assignee })
    : undefined
  const description = issue.description
    ? await client.fetchMarkup(issue._class, issue._id, 'description', issue.description, 'markdown')
    : ''
  const comments = await client.findAll(chunter.class.ChatMessage, { attachedTo: issue._id })

  const lines = [
    `${issue.identifier}: ${issue.title}`,
    `status: ${status?.name ?? 'unknown'}`,
    `priority: ${priorityName ?? 'unknown'}`,
    `category: ${component?.label ?? '(none)'}`,
    `assignee: ${assignee?.name ?? '(unassigned)'}`,
    `due: ${formatDueDate(issue.dueDate)}`
  ]
  if (description.trim().length > 0) {
    lines.push('', description.trim())
  }
  if (comments.length > 0) {
    lines.push('', `${comments.length} comment(s):`)
    for (const c of comments.slice(-5)) lines.push(`- ${c.message}`)
  }
  return { text: lines.join('\n'), identifier: issue.identifier }
}

const DEFAULT_CATEGORIES = ['Bug', 'Feature', 'Chore', 'Research']

async function ensureCategories (client, project) {
  const existing = await client.findAll(tracker.class.Component, { space: project._id })
  if (existing.length > 0) return existing.slice(0, 4)

  const created = []
  for (const label of DEFAULT_CATEGORIES) {
    const id = generateId()
    await client.createDoc(tracker.class.Component, project._id, {
      label,
      description: '',
      lead: null,
      comments: 0,
      attachments: 0
    }, id)
    created.push({ _id: id, label })
  }
  return created
}

async function createIssue (title) {
  const client = await getHulyClient()
  const project = await getProject(client)

  const issueId = generateId()
  const inc = await client.updateDoc(
    tracker.class.Project, core.space.Space, project._id, { $inc: { sequence: 1 } }, true
  )
  const sequence = inc.object.sequence

  const lastOne = await client.findOne(
    tracker.class.Issue, { space: project._id }, { sort: { rank: SortingOrder.Descending } }
  )

  const description = await client.uploadMarkup(tracker.class.Issue, issueId, 'description', '', 'markdown')
  const identifier = `${project.identifier}-${sequence}`

  await client.addCollection(
    tracker.class.Issue, project._id, project._id, project._class, 'issues',
    {
      title,
      description,
      status: project.defaultIssueStatus,
      number: sequence,
      kind: tracker.taskTypes.Issue,
      identifier,
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
  return { issueId, identifier, project }
}

async function setStatus (identifier, name) {
  const client = await getHulyClient()
  const issue = await findIssueByIdentifier(client, identifier)

  const aliases = {
    backlog: tracker.status.Backlog,
    todo: tracker.status.Todo,
    'in progress': tracker.status.InProgress,
    inprogress: tracker.status.InProgress,
    done: tracker.status.Done,
    cancelled: tracker.status.Canceled,
    canceled: tracker.status.Canceled
  }
  const statusRef = aliases[name.trim().toLowerCase()]
  if (statusRef === undefined) {
    throw new Error(`unknown status "${name}" — try: backlog, todo, in progress, done, cancelled`)
  }
  await client.updateDoc(tracker.class.Issue, issue.space, issue._id, { status: statusRef })
}

async function setPriority (identifier, name) {
  const client = await getHulyClient()
  const issue = await findIssueByIdentifier(client, identifier)

  const key = name.trim().toLowerCase()
  const match = Object.keys(IssuePriority).find(
    (k) => isNaN(Number(k)) && k.toLowerCase() === (key === 'none' ? 'nopriority' : key)
  )
  if (match === undefined) {
    throw new Error(`unknown priority "${name}" — try: urgent, high, medium, low, none`)
  }
  await client.updateDoc(tracker.class.Issue, issue.space, issue._id, { priority: IssuePriority[match] })
}

async function assignIssue (identifier, name) {
  const client = await getHulyClient()
  const issue = await findIssueByIdentifier(client, identifier)

  const people = await client.findAll(contact.class.Person, {})
  const needle = name.trim().toLowerCase()
  const matches = people.filter((p) => (p.name ?? '').toLowerCase().includes(needle))

  if (matches.length === 0) throw new Error(`no workspace member matching "${name}"`)
  if (matches.length > 1) {
    const names = matches.map((p) => p.name).join(', ')
    throw new Error(`multiple members match "${name}": ${names} — be more specific`)
  }

  await client.updateDoc(tracker.class.Issue, issue.space, issue._id, { assignee: matches[0]._id })
  return matches[0].name
}

function parseDueDate (input) {
  const key = input.trim().toLowerCase()
  const now = new Date()
  if (key === 'today') return new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()
  if (key === 'tomorrow') return new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1).getTime()
  const parsed = Date.parse(input.trim())
  if (isNaN(parsed)) throw new Error(`unrecognized date "${input}" — try: today, tomorrow, or YYYY-MM-DD`)
  return parsed
}

async function setDueDate (identifier, dateStr) {
  const client = await getHulyClient()
  const issue = await findIssueByIdentifier(client, identifier)
  const ts = parseDueDate(dateStr)
  await client.updateDoc(tracker.class.Issue, issue.space, issue._id, { dueDate: ts })
  return formatDueDate(ts)
}

async function addComment (identifier, text) {
  const client = await getHulyClient()
  const issue = await findIssueByIdentifier(client, identifier)
  const commentId = generateId()
  await client.addCollection(
    chunter.class.ChatMessage, issue.space, issue._id, issue._class, 'comments',
    { message: text }, commentId
  )
}

async function deleteIssue (identifier) {
  const client = await getHulyClient()
  const issue = await findIssueByIdentifier(client, identifier)
  await client.removeDoc(tracker.class.Issue, issue.space, issue._id)
}

// In-memory: short callback keys -> pending categorization context. Lost on
// restart, which just means an in-flight suggestion has to be redone — low
// stakes for a personal tool.
const pendingCategorization = new Map()

async function suggestCategories (chatId, issueId, identifier, title) {
  const client = await getHulyClient()
  const project = await getProject(client)
  const categories = await ensureCategories(client, project)

  const key = generateId().slice(0, 10)
  pendingCategorization.set(key, { issueId, projectSpace: project._id })

  const buttons = categories.map((c, i) => ([{ text: c.label, callback_data: `cat:${key}:${i}` }]))
  buttons.push([{ text: 'Skip', callback_data: `skip:${key}` }])
  pendingCategorization.get(key).options = categories

  await sendMessage(chatId, `Pick a category for ${identifier}: ${title}`, {
    reply_markup: { inline_keyboard: buttons }
  })
}

async function handleCallbackQuery (query) {
  const userId = query.from?.id
  if (String(userId) !== String(TELEGRAM_ALLOWED_USER_ID)) {
    console.warn(`ignoring callback from unauthorized user id ${userId}`)
    return
  }

  const data = query.data ?? ''
  const chatId = query.message?.chat?.id
  const messageId = query.message?.message_id

  if (data.startsWith('skip:')) {
    const key = data.slice('skip:'.length)
    pendingCategorization.delete(key)
    await answerCallbackQuery(query.id, 'Skipped')
    if (chatId !== undefined) await editMessageText(chatId, messageId, 'Skipped categorization.')
    return
  }

  if (data.startsWith('cat:')) {
    const [, key, indexStr] = data.split(':')
    const pending = pendingCategorization.get(key)
    if (pending === undefined) {
      await answerCallbackQuery(query.id, 'This suggestion expired')
      return
    }
    const category = pending.options[Number(indexStr)]
    try {
      const client = await getHulyClient()
      const issue = await client.findOne(tracker.class.Issue, { _id: pending.issueId })
      if (issue === undefined) throw new Error('issue no longer exists')
      await client.updateDoc(tracker.class.Issue, pending.projectSpace, issue._id, {
        component: category._id,
        title: `[${category.label}] ${issue.title}`
      })
      pendingCategorization.delete(key)
      await answerCallbackQuery(query.id, `Categorized as ${category.label}`)
      if (chatId !== undefined) {
        await editMessageText(chatId, messageId, `Categorized ${issue.identifier} as ${category.label}.`)
      }
    } catch (err) {
      console.error(err)
      await answerCallbackQuery(query.id, `Failed: ${err.message}`)
    }
    return
  }

  if (data.startsWith('done:')) {
    const identifier = data.slice('done:'.length)
    try {
      await setStatus(identifier, 'done')
      await answerCallbackQuery(query.id, `${identifier} marked Done`)
      if (chatId !== undefined) await editMessageText(chatId, messageId, `${identifier} marked Done.`)
    } catch (err) {
      await answerCallbackQuery(query.id, `Failed: ${err.message}`)
    }
    return
  }

  if (data.startsWith('highpri:')) {
    const identifier = data.slice('highpri:'.length)
    try {
      await setPriority(identifier, 'high')
      await answerCallbackQuery(query.id, `${identifier} set to High priority`)
      if (chatId !== undefined) await editMessageText(chatId, messageId, `${identifier} set to High priority.`)
    } catch (err) {
      await answerCallbackQuery(query.id, `Failed: ${err.message}`)
    }
    return
  }

  if (data.startsWith('delask:')) {
    const identifier = data.slice('delask:'.length)
    await answerCallbackQuery(query.id)
    if (chatId !== undefined) {
      await editMessageText(chatId, messageId, `Delete ${identifier}? This can't be undone.`, {
        reply_markup: {
          inline_keyboard: [[
            { text: 'Confirm Delete', callback_data: `delyes:${identifier}` },
            { text: 'Cancel', callback_data: `delno:${identifier}` }
          ]]
        }
      })
    }
    return
  }

  if (data.startsWith('delyes:')) {
    const identifier = data.slice('delyes:'.length)
    try {
      await deleteIssue(identifier)
      await answerCallbackQuery(query.id, `${identifier} deleted`)
      if (chatId !== undefined) await editMessageText(chatId, messageId, `${identifier} deleted.`)
    } catch (err) {
      await answerCallbackQuery(query.id, `Failed: ${err.message}`)
    }
    return
  }

  if (data.startsWith('delno:')) {
    const identifier = data.slice('delno:'.length)
    await answerCallbackQuery(query.id, 'Cancelled')
    if (chatId !== undefined) await editMessageText(chatId, messageId, `Delete cancelled for ${identifier}.`)
  }
}

const HELP_TEXT = [
  '/tasks - list the 10 most recently updated issues',
  '/find <keyword> - search issue titles',
  '/task <ID> - full details + quick-action buttons',
  '/add <text> - create a new issue, then suggests a category',
  '/status <ID> <name> - backlog | todo | in progress | done | cancelled',
  '/priority <ID> <name> - urgent | high | medium | low | none',
  '/assign <ID> <name> - assign to a workspace member',
  '/due <ID> <date> - today | tomorrow | YYYY-MM-DD',
  '/comment <ID> <text> - add a comment',
  '/delete <ID> - delete an issue'
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
      await sendMessage(chatId, await listRecentIssues())
    } catch (err) {
      console.error(err)
      await sendMessage(chatId, `failed to list issues: ${err.message}`)
    }
    return
  }

  if (text.startsWith('/find ')) {
    const keyword = text.slice('/find '.length).trim()
    try {
      await sendMessage(chatId, await findIssues(keyword))
    } catch (err) {
      console.error(err)
      await sendMessage(chatId, `failed to search: ${err.message}`)
    }
    return
  }

  if (text.startsWith('/task ')) {
    const identifier = text.slice('/task '.length).trim()
    try {
      const { text: details } = await getIssueDetails(identifier)
      await sendMessage(chatId, details, taskActionButtons(identifier))
    } catch (err) {
      console.error(err)
      await sendMessage(chatId, `failed to get task: ${err.message}`)
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
      const { issueId, identifier } = await createIssue(title)
      await sendMessage(chatId, `created ${identifier}: ${title}`)
      await suggestCategories(chatId, issueId, identifier, title)
    } catch (err) {
      console.error(err)
      await sendMessage(chatId, `failed to create issue: ${err.message}`)
    }
    return
  }

  if (text.startsWith('/status ')) {
    const rest = text.slice('/status '.length).trim()
    const [identifier, ...nameParts] = rest.split(' ')
    try {
      await setStatus(identifier, nameParts.join(' '))
      await sendMessage(chatId, `updated ${identifier} status`)
    } catch (err) {
      console.error(err)
      await sendMessage(chatId, `failed to set status: ${err.message}`)
    }
    return
  }

  if (text.startsWith('/priority ')) {
    const rest = text.slice('/priority '.length).trim()
    const [identifier, ...nameParts] = rest.split(' ')
    try {
      await setPriority(identifier, nameParts.join(' '))
      await sendMessage(chatId, `updated ${identifier} priority`)
    } catch (err) {
      console.error(err)
      await sendMessage(chatId, `failed to set priority: ${err.message}`)
    }
    return
  }

  if (text.startsWith('/assign ')) {
    const rest = text.slice('/assign '.length).trim()
    const [identifier, ...nameParts] = rest.split(' ')
    const name = nameParts.join(' ')
    if (name.length === 0) {
      await sendMessage(chatId, 'usage: /assign <ID> <name>')
      return
    }
    try {
      const assignedName = await assignIssue(identifier, name)
      await sendMessage(chatId, `assigned ${identifier} to ${assignedName}`)
    } catch (err) {
      console.error(err)
      await sendMessage(chatId, `failed to assign: ${err.message}`)
    }
    return
  }

  if (text.startsWith('/due ')) {
    const rest = text.slice('/due '.length).trim()
    const [identifier, ...dateParts] = rest.split(' ')
    const dateStr = dateParts.join(' ')
    if (dateStr.length === 0) {
      await sendMessage(chatId, 'usage: /due <ID> <today|tomorrow|YYYY-MM-DD>')
      return
    }
    try {
      const formatted = await setDueDate(identifier, dateStr)
      await sendMessage(chatId, `set ${identifier} due date to ${formatted}`)
    } catch (err) {
      console.error(err)
      await sendMessage(chatId, `failed to set due date: ${err.message}`)
    }
    return
  }

  if (text.startsWith('/comment ')) {
    const rest = text.slice('/comment '.length).trim()
    const [identifier, ...commentParts] = rest.split(' ')
    const comment = commentParts.join(' ')
    if (comment.length === 0) {
      await sendMessage(chatId, 'usage: /comment <ID> <text>')
      return
    }
    try {
      await addComment(identifier, comment)
      await sendMessage(chatId, `added comment to ${identifier}`)
    } catch (err) {
      console.error(err)
      await sendMessage(chatId, `failed to add comment: ${err.message}`)
    }
    return
  }

  if (text.startsWith('/delete ')) {
    const identifier = text.slice('/delete '.length).trim()
    try {
      await deleteIssue(identifier)
      await sendMessage(chatId, `deleted ${identifier}`)
    } catch (err) {
      console.error(err)
      await sendMessage(chatId, `failed to delete: ${err.message}`)
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
      } else if (update.callback_query !== undefined) {
        await handleCallbackQuery(update.callback_query).catch((err) => console.error('handleCallbackQuery error:', err))
      }
    }
  }
}

pollLoop().catch((err) => {
  console.error('fatal:', err)
  process.exit(1)
})
