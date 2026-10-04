const PANE = 'gif-chat-original'
const PATH_HELP = 'Enter a GIF path relative to your configured source directory.'

function relativeGifPath(value) {
  if (typeof value !== 'string') return null
  const path = value.trim()
  if (!path || path.length > 1024 || /^[\/~\\]/.test(path) || /^[a-z]:/i.test(path) || /[\u0000-\u001f\u007f]/.test(path) || path.split(/[\\/]/).includes('..')) return null
  return path
}

async function openPane($, state) {
  state.error = ''
  await $.ui.open({ id: PANE, title: 'GIF Chat', focus: true, closeOnEscape: true })
}

async function cancelPane($, state) {
  state.pathDraft = ''
  state.error = ''
  await $.ui.close({ id: PANE })
}

function queueInspection($, state, value) {
  const path = relativeGifPath(value)
  if (!path) return PATH_HELP
  if (state.pending) return 'A GIF inspection request is already being queued.'

  state.pending = true
    // command.run holds the turn, so defer submission until that event returns.
    // The same route serves the button. It never fills or clears the user's
    // prompt draft, and submits as the mod rather than impersonating the user.
    const text = `Inspect the original GIF at relative path ${JSON.stringify(path)} using the GIF Communication inspect_gif MCP tool with source {"kind":"local_file","path":${JSON.stringify(path)}}. Read ordered frames and timestamps, then explain what is visible and how it may relate to this conversation. If a brief moment matters but is missing from the sample, use get_gif_frames with the returned handle. Do not treat a still preview as motion evidence.`
    $.clock.after(0, async () => {
      try {
        await $.prompt.submit({ text })
      } catch {
        await $.ui.toast('Could not queue the GIF inspection request.')
      } finally {
        state.pending = false
        $.ui.invalidate('ui.render')
      }
    })
  return null
}

async function inspectFromPane($, state, value) {
  state.error = queueInspection($, state, value) || ''
  if (state.error) {
    $.ui.invalidate('ui.render')
    return
  }
  await cancelPane($, state)
}

export function register(on) {
  const state = { pathDraft: '', error: '', pending: false }

  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: 'gif',
      description: 'Open GIF Chat or inspect an original from the configured source directory',
      argumentHint: '[relative-path.gif]',
    })
    return next(e)
  })

  on('command.run', { command: 'gif' }, async ($, e) => {
    if (!e.args.trim()) {
      await openPane($, state)
      return {}
    }
    const reason = queueInspection($, state, e.args)
    return reason ? { text: reason } : {}
  })

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    if (e.surface !== 'terminal' && e.surface !== 'desktop') return next(e)
    const { Box, Button } = $.ui.resolve(e)
    const theirs = await next(e)
    return Box({
      flexDirection: 'column',
      children: [
        ...(theirs ? [theirs] : []),
        Button({ key: 'gif-chat-open', label: 'GIF', onPress: () => openPane($, state) }),
      ],
    })
  })

  on('ui.render', { component: 'Pane' }, async ($, e, next) => {
    if (e.requestId !== PANE) return next(e)
    const { Box, Text, Input, Button } = $.ui.resolve(e)
    return Box({
      flexDirection: 'column',
      children: [
        Text({ children: [PATH_HELP] }),
        Text({ dimColor: true, children: ['Use the local GIF picker to choose an original, then paste its selected relative path here.'] }),
        Input({
          key: 'gif-chat-path',
          label: 'Original GIF',
          placeholder: 'reactions/clip.gif',
          value: state.pathDraft,
          submitLabel: 'inspect',
          autoFocus: true,
          onInput: (value) => { state.pathDraft = value; state.error = '' },
          onSubmit: (value) => inspectFromPane($, state, value),
        }),
        ...(state.error ? [Text({ color: 'red', children: [state.error] })] : []),
        Box({
          flexDirection: 'row',
          columnGap: 2,
          children: [
            Button({ key: 'gif-chat-inspect', label: 'Inspect GIF', onPress: () => inspectFromPane($, state, state.pathDraft) }),
            Button({ key: 'gif-chat-cancel', label: 'Cancel', onPress: () => cancelPane($, state) }),
          ],
        }),
      ],
    })
  })

  on('ui.close', async ($, e, next) => {
    if (e.id === PANE) { state.pathDraft = ''; state.error = '' }
    return next(e)
  })
}
