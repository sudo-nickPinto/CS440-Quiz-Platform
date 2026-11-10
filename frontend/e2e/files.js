// Just enough CSV and .xlsx reading to check the exports in the e2e tests,
// without adding a spreadsheet dependency.

import { inflateRawSync } from 'node:zlib'

// Rows of fields from CSV bytes (Python's csv module: quotes, CRLF).
export function readCsv(bytes) {
  const text = bytes.toString('utf8').replace(/^\uFEFF/, '')
  const rows = []
  let row = []
  let field = ''
  let quoted = false
  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i]
    if (quoted) {
      if (ch !== '"') field += ch
      else if (text[i + 1] === '"') field += text[(i += 1)]
      else quoted = false
    } else if (ch === '"') {
      quoted = true
    } else if (ch === ',') {
      row.push(field)
      field = ''
    } else if (ch === '\n') {
      row.push(field)
      rows.push(row)
      row = []
      field = ''
    } else if (ch !== '\r') {
      field += ch
    }
  }
  if (field || row.length) rows.push([...row, field])
  return rows
}

// { name: text } for every file in a zip archive.
function unzip(bytes) {
  const end = bytes.lastIndexOf(Buffer.from([0x50, 0x4b, 0x05, 0x06]))
  const count = bytes.readUInt16LE(end + 10)
  let offset = bytes.readUInt32LE(end + 16)
  const files = {}
  for (let i = 0; i < count; i += 1) {
    const method = bytes.readUInt16LE(offset + 10)
    const size = bytes.readUInt32LE(offset + 20)
    const nameLength = bytes.readUInt16LE(offset + 28)
    const extraLength = bytes.readUInt16LE(offset + 30)
    const commentLength = bytes.readUInt16LE(offset + 32)
    const local = bytes.readUInt32LE(offset + 42)
    const name = bytes.toString('utf8', offset + 46, offset + 46 + nameLength)
    const start = local + 30 + bytes.readUInt16LE(local + 26) + bytes.readUInt16LE(local + 28)
    const data = bytes.subarray(start, start + size)
    files[name] = (method === 8 ? inflateRawSync(data) : data).toString('utf8')
    offset += 46 + nameLength + extraLength + commentLength
  }
  return files
}

const ENTITIES = { lt: '<', gt: '>', quot: '"', apos: "'", amp: '&' }
const unescape = (text) => text.replace(/&(lt|gt|quot|apos|amp);/g, (_, name) => ENTITIES[name])
const attr = (tag, name) => tag.match(new RegExp(`\\s${name}="([^"]*)"`))?.[1]
const texts = (xml) => [...xml.matchAll(/<t(?:\s[^>]*)?>([^<]*)<\/t>/g)].map(([, t]) => unescape(t)).join('')

function column(letters) {
  return [...letters].reduce((n, ch) => n * 26 + ch.charCodeAt(0) - 64, 0) - 1
}

// { sheets: { name: rows }, sheetNames, formulas } from .xlsx bytes. Rows are
// arrays of cell values (strings and numbers; null for an empty cell).
export function readXlsx(bytes) {
  const files = unzip(bytes)
  const shared = [...(files['xl/sharedStrings.xml'] ?? '').matchAll(/<si>(.*?)<\/si>/gs)].map(
    ([, si]) => texts(si),
  )
  const targets = {}
  for (const [tag] of files['xl/_rels/workbook.xml.rels'].matchAll(/<Relationship\s[^>]*>/g)) {
    const target = attr(tag, 'Target').replace(/^\//, '')
    targets[attr(tag, 'Id')] = target.startsWith('xl/') ? target : `xl/${target}`
  }

  const sheets = {}
  let formulas = 0
  for (const [tag] of files['xl/workbook.xml'].matchAll(/<sheet\s[^>]*>/g)) {
    const xml = files[targets[attr(tag, 'r:id')]]
    formulas += (xml.match(/<f[\s>]/g) ?? []).length
    const rows = []
    for (const [, letters, number, attrs, body = ''] of xml.matchAll(
      /<c r="([A-Z]+)(\d+)"([^>]*?)(?:\/>|>(.*?)<\/c>)/gs,
    )) {
      const type = attr(attrs, 't')
      const value = body.match(/<v>([^<]*)<\/v>/)?.[1]
      let cell = null
      if (type === 's') cell = shared[Number(value)]
      else if (type === 'inlineStr') cell = texts(body)
      else if (type === 'str') cell = unescape(value ?? '')
      else if (value !== undefined) cell = Number(value)
      const row = (rows[Number(number) - 1] ??= [])
      row[column(letters)] = cell
    }
    sheets[unescape(attr(tag, 'name'))] = Array.from(rows, (row = []) =>
      Array.from(row, (cell) => cell ?? null),
    )
  }
  return { sheets, sheetNames: Object.keys(sheets), formulas }
}
