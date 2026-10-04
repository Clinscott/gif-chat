import { expect, mock, test } from 'claude-code/testing'

const BAND = {
  plugin: 'gif-chat',
  component: 'AbovePrompt',
  requestId: 'above-prompt',
  viewport: { columns: 100, rows: 30 },
  props: { hasSurvey: false, isWorking: false, maxRows: 4, bodyColumns: 80, scroll: { offset: 0, bodyRows: 4 }, view: {} },
} as const

const PANE = {
  plugin: 'gif-chat',
  component: 'Pane',
  requestId: 'gif-chat-original',
  viewport: { columns: 100, rows: 30 },
  props: { title: 'GIF Chat', isFocused: true, bodyColumns: 80, placement: 'inline', scroll: { offset: 0, bodyRows: 10 }, view: {} },
} as const

test('/gif registers an explicit command', async ($, on) => {
  let name = ''
  on('session.start', () => ({ cwd: '/work' }))
  on('command.register', ($, e) => {
    name = e.name
    return { value: undefined }
  })

  await $.session.start({ surface: 'terminal', isInteractive: true, cwd: '/work' })
  expect(name).toBe('gif')
})

test('/gif queues one task-local request for a relative original', async ($, on) => {
  const submitted: string[] = []
  const toasts: string[] = []
  const clock = mock.clock(on)
  on('prompt.submit', ($, e) => {
    submitted.push(e.text)
    return { text: e.text }
  })
  on('ui.toast', ($, e) => {
    toasts.push(e.text)
    return { value: undefined }
  })

  const answer = await $.command.run({ command: 'gif', args: 'reactions/clip.gif' })
  await clock.settle()
  expect(answer).toEqual({})
  expect(toasts).toEqual([])
  expect(submitted.length).toBe(1)
  expect(submitted[0]).toContain('"kind":"local_file","path":"reactions/clip.gif"')
})

test('/gif rejects an absolute or parent-traversing path without a new request', async ($, on) => {
  const submitted: string[] = []
  const clock = mock.clock(on)
  on('prompt.submit', ($, e) => {
    submitted.push(e.text)
    return { text: e.text }
  })

  const absolute = await $.command.run({ command: 'gif', args: '/tmp/clip.gif' })
  const traversal = await $.command.run({ command: 'gif', args: '../clip.gif' })
  await clock.settle()
  expect(absolute.text).toContain('relative')
  expect(traversal.text).toContain('relative')
  expect(submitted).toEqual([])
})

test('the GIF button preserves the shared band and opens a pane without submitting or changing a draft', async ($, on) => {
  const opened: string[] = []
  const submitted: string[] = []
  const filled: string[] = []
  on('ui.render', () => ({ type: 'Text', props: {}, children: ['another mod'] }))
  on('ui.open', ($, e) => { opened.push(e.id); return { value: { isPlaced: true } } })
  on('prompt.submit', ($, e) => { submitted.push(e.text); return { text: e.text } })
  on('prompt.fill', ($, e) => { filled.push(e.text); return { isFilled: true } })

  for (const surface of ['terminal', 'desktop'] as const) {
    const ui = await $.ui.mount({ ...BAND, surface })
    expect(await ui.find({ type: 'Text', text: 'another mod' })).toBeDefined()
    expect(submitted).toEqual([])
    await ui.press({ key: 'gif-chat-open' })
    await ui.unmount()
  }
  expect(opened).toEqual(['gif-chat-original', 'gif-chat-original'])
  expect(submitted).toEqual([])
  expect(filled).toEqual([])
})

test('the path input queues exactly one request even when submitted twice before the timer runs', async ($, on) => {
  const submitted: string[] = []
  const closed: string[] = []
  const clock = mock.clock(on)
  on('prompt.submit', ($, e) => { submitted.push(e.text); return { text: e.text } })
  on('ui.close', ($, e) => { closed.push(e.id); return { value: undefined } })
  on('ui.toast', () => ({ value: undefined }))

  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  await ui.input({ key: 'gif-chat-path', text: 'reactions/clip.gif' })
  await ui.input({ key: 'gif-chat-path', text: 'reactions/clip.gif' })
  expect(submitted).toEqual([])
  await clock.settle()
  expect(submitted.length).toBe(1)
  expect(submitted[0]).toContain('"kind":"local_file","path":"reactions/clip.gif"')
  expect(closed).toEqual(['gif-chat-original'])
})

test('typing a path and cancelling closes the pane without a request', async ($, on) => {
  const submitted: string[] = []
  const closed: string[] = []
  const clock = mock.clock(on)
  on('prompt.submit', ($, e) => { submitted.push(e.text); return { text: e.text } })
  on('ui.close', ($, e) => { closed.push(e.id); return { value: undefined } })

  const ui = await $.ui.mount({ ...PANE, surface: 'desktop' })
  await ui.input({ key: 'gif-chat-path', text: 'reactions/clip.gif', kind: 'change' })
  await ui.press({ key: 'gif-chat-cancel' })
  await clock.settle()
  expect(submitted).toEqual([])
  expect(closed).toEqual(['gif-chat-original'])
})

test('the pane rejects unsafe paths and Inspect uses the typed relative original', async ($, on) => {
  const submitted: string[] = []
  const clock = mock.clock(on)
  on('prompt.submit', ($, e) => { submitted.push(e.text); return { text: e.text } })
  on('ui.close', () => ({ value: undefined }))
  on('ui.toast', () => ({ value: undefined }))

  const ui = await $.ui.mount({ ...PANE, surface: 'desktop' })
  for (const text of ['/tmp/a.gif', '../a.gif', 'C:\\a.gif', '..\\a.gif', 'a\n.gif', 'x'.repeat(1025)]) {
    await ui.input({ key: 'gif-chat-path', text })
  }
  await clock.settle()
  expect(submitted).toEqual([])
  await ui.input({ key: 'gif-chat-path', text: 'reactions/clip.gif', kind: 'change' })
  await ui.press({ key: 'gif-chat-inspect' })
  await clock.settle()
  expect(submitted.length).toBe(1)
  expect(submitted[0]).toContain('"path":"reactions/clip.gif"')
})

test('a failed prompt submission reports one toast and does not retry', async ($, on) => {
  let attempts = 0
  const toasts: string[] = []
  const clock = mock.clock(on)
  on('prompt.submit', () => { attempts += 1; return { deny: 'offline refusal' } })
  on('ui.toast', ($, e) => { toasts.push(e.text); return { value: undefined } })
  await $.command.run({ command: 'gif', args: 'reactions/clip.gif' })
  await clock.settle()
  expect(attempts).toBe(1)
  expect(toasts).toEqual(['Could not queue the GIF inspection request.'])
})
