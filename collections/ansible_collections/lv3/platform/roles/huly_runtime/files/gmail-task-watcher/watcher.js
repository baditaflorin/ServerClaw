// Pulls Gmail push notifications from a Pub/Sub subscription, matches the
// message subject against a configurable list of { pattern, project } rules
// (not hardcoded to any one team/tag), and creates a Huly Tracker issue for
// each match.
'use strict'

const fs = require('fs')
const { PubSub } = require('@google-cloud/pubsub')
const { google } = require('googleapis')
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
const GOOGLE_CLIENT_ID = required('GOOGLE_CLIENT_ID')
const GOOGLE_CLIENT_SECRET = required('GOOGLE_CLIENT_SECRET')
const GOOGLE_REFRESH_TOKEN = required('GOOGLE_REFRESH_TOKEN')
const GCP_PROJECT_ID = required('GCP_PROJECT_ID')
const PUBSUB_SUBSCRIPTION = required('PUBSUB_SUBSCRIPTION')
const RULES_FILE = required('GMAIL_TASK_RULES_FILE')
const STATE_FILE = process.env.STATE_FILE ?? '/data/state.json'

function required (name) {
  const v = process.env[name]
  if (!v) {
    console.error(`missing required env var: ${name}`)
    process.exit(1)
  }
  return v
}

function loadRules () {
  const raw = JSON.parse(fs.readFileSync(RULES_FILE, 'utf8'))
  if (!Array.isArray(raw.rules)) throw new Error(`${RULES_FILE} must contain {"rules": [{"pattern":..,"project":..}]}`)
  return raw.rules
}

function loadState () {
  try {
    return JSON.parse(fs.readFileSync(STATE_FILE, 'utf8'))
  } catch {
    return { lastHistoryId: null }
  }
}

function saveState (state) {
  fs.mkdirSync(require('path').dirname(STATE_FILE), { recursive: true })
  fs.writeFileSync(STATE_FILE, JSON.stringify(state))
}

const oAuth2Client = new google.auth.OAuth2(GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET)
oAuth2Client.setCredentials({ refresh_token: GOOGLE_REFRESH_TOKEN })
const gmail = google.gmail({ version: 'v1', auth: oAuth2Client })

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

function matchRule (subject, rules) {
  const lower = subject.toLowerCase()
  return rules.find((r) => lower.includes(r.pattern.toLowerCase()))
}

function stripTag (subject, pattern) {
  const idx = subject.toLowerCase().indexOf(pattern.toLowerCase())
  if (idx === -1) return subject.trim()
  return (subject.slice(0, idx) + subject.slice(idx + pattern.length)).trim()
}

async function createIssue (projectIdentifier, title) {
  const client = await getHulyClient()
  const project = await client.findOne(tracker.class.Project, { identifier: projectIdentifier })
  if (project === undefined) {
    console.error(`project ${projectIdentifier} not found, skipping: ${title}`)
    return
  }

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
  console.log(`created ${project.identifier}-${sequence}: ${title}`)
}

async function processNewMessages (rules) {
  const state = loadState()
  if (state.lastHistoryId === null) {
    // First run: nothing to diff against yet. Seed from the current profile
    // historyId so we only act on mail that arrives from now on.
    const profile = await gmail.users.getProfile({ userId: 'me' })
    state.lastHistoryId = profile.data.historyId
    saveState(state)
    console.log(`seeded lastHistoryId=${state.lastHistoryId}, waiting for new mail`)
    return
  }

  let pageToken
  const messageIds = new Set()
  let newestHistoryId = state.lastHistoryId

  do {
    const res = await gmail.users.history.list({
      userId: 'me',
      startHistoryId: state.lastHistoryId,
      historyTypes: ['messageAdded'],
      pageToken
    })
    for (const h of res.data.history ?? []) {
      for (const added of h.messagesAdded ?? []) {
        messageIds.add(added.message.id)
      }
      if (h.id && Number(h.id) > Number(newestHistoryId)) newestHistoryId = h.id
    }
    pageToken = res.data.nextPageToken
  } while (pageToken)

  for (const id of messageIds) {
    const msg = await gmail.users.messages.get({ userId: 'me', id, format: 'metadata', metadataHeaders: ['Subject'] })
    const subjectHeader = msg.data.payload?.headers?.find((h) => h.name === 'Subject')
    const subject = subjectHeader?.value ?? '(no subject)'
    const rule = matchRule(subject, rules)
    if (rule === undefined) continue
    await createIssue(rule.project, stripTag(subject, rule.pattern))
  }

  state.lastHistoryId = newestHistoryId
  saveState(state)
}

async function main () {
  const rules = loadRules()
  console.log(`huly-gmail-task-watcher: loaded ${rules.length} rule(s), subscribing to ${PUBSUB_SUBSCRIPTION}`)

  const pubsub = new PubSub({ projectId: GCP_PROJECT_ID })
  const subscription = pubsub.subscription(PUBSUB_SUBSCRIPTION)

  subscription.on('message', (message) => {
    message.ack()
    processNewMessages(rules).catch((err) => console.error('processNewMessages error:', err))
  })
  subscription.on('error', (err) => console.error('subscription error:', err))
}

main().catch((err) => {
  console.error('fatal:', err)
  process.exit(1)
})
