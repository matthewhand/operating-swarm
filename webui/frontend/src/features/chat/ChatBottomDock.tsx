/**
 * #856 slice H — the chat bottom dock, moved verbatim from ChatPage.tsx.
 *
 * Renders everything under the message list: demo/suggestion chips, the
 * connection-status banner, the context-usage badge, and the composer form
 * (slash popup, provider pill, attachments tray, input, mic, send/stop).
 * ChatPage owns all state and passes it down as one props object.
 */

import { useCallback, useState } from 'react'
import { Sparkles } from 'lucide-react'
import { enhancePrompt } from '../../lib/api'

export interface ChatBottomDockProps {
  [key: string]: any
}

export const ChatBottomDock = function ChatBottomDock(props: ChatBottomDockProps) {
    const { ArrowUp, ChatMessageInput, ComposerAttachChips, ComposerPluginsBadge, ComposerPluginsPanel, ComposerSlashPopup, ContextUsageBadge, Layers, Mic, Paperclip, Plug, Plus, QueuedSendPane, Reply, Square, SuggestionChips, addToast, authRejected, awaitingAssistant, bottomDockRef, chipsDisabled, chooseSuggestion, composerBusy, composerDragOver, composerMenu, composerPlaceholder, composerRef, composerWrapRef, contextUsage, conversationId, demoChips, describeSpeechPath, enqueueComposerFiles, fileInputRef, filesFromList, filteredSlashItems, generationIsInFlight, handleCompact, handleComposerDragEnter, handleComposerDragLeave, handleComposerDragOver, handleComposerDrop, handleComposerKeyDown, handleComposerPaste, handleInputChange, handleMic, handleSelectSlashItem, handleSend, hasSendableDraft, input, interruptRunningTurn, isApiAgent, isSlashOpen, messages, pendingAttachments, pluginsPanelOpen, plusOpen, plusRef, queued, queuedPaneMaxHeightPx, recentSlashIds, removeAttachment, renderRoutingPicker, replyTarget, selectedBlueprint, sendNowHint, setInput, setPluginsPanelOpen, setPlusOpen, setQueuedHoldIds, setReplyTarget, setSlashSelectedIndex, setTokenDiagOpen, showContextUsage, showDemoChips, showSuggestionChips, slashQuery, slashSelectedIndex, status, sttListening, sttPathUsed, suggestionChips, transcriptHeightPx } = props as any
    const SparklesIcon = props.Sparkles || Sparkles
    const [enhancingLocal, setEnhancingLocal] = useState(false)
    const enhancing = props.enhancing ?? enhancingLocal

    const defaultHandleEnhance = useCallback(async () => {
      const draft = (input || '').trim()
      if (!draft || enhancing) return
      setEnhancingLocal(true)
      setPlusOpen(false)
      try {
        const res = await enhancePrompt(draft)
        const enhanced = (res.enhanced || '').trim()
        if (enhanced) {
          setInput(enhanced)
          requestAnimationFrame(() => {
            if (composerRef?.current) {
              composerRef.current.focus()
              const len = enhanced.length
              composerRef.current.setSelectionRange(len, len)
            }
          })
        }
      } catch {
        addToast({
          type: 'error',
          title: 'Enhance prompt',
          message: 'The model could not enhance this draft. Try again shortly.',
        })
      } finally {
        setEnhancingLocal(false)
      }
    }, [addToast, composerRef, enhancing, input, setInput, setPlusOpen])

    const handleEnhance = props.handleEnhance || defaultHandleEnhance

  return (
    <>
        <div
          ref={bottomDockRef}
          className="os-chat-bottom-dock sticky bottom-0 z-20 -mx-2 sm:-mx-3 -mb-3 bg-base-100 border-t border-base-content/5"
          data-testid="chat-bottom-dock"
        >

          {showDemoChips ? (
            <SuggestionChips
              chips={demoChips}
              disabled={chipsDisabled}
              onChoose={chooseSuggestion}
            />
          ) : showSuggestionChips ? (
            <SuggestionChips
              chips={suggestionChips}
              disabled={chipsDisabled}
              onChoose={chooseSuggestion}
            />
          ) : null}
          <ComposerPluginsBadge />
          {status !== 'open' ? (
            <div
              className="os-conn-status"
              data-testid="chat-conn-status"
              aria-live="polite"
            >
              <span className="os-conn-status__dot" aria-hidden="true" />
              <span className="os-conn-status__label">
                {authRejected
                  ? 'Sign in to chat — your draft is kept locally.'
                  : 'Chat is offline — you can keep typing; sends will queue until it reconnects.'}
              </span>
            </div>
          ) : null}
          {showContextUsage && contextUsage ? (
            <div
              className="flex justify-end px-3 pt-1.5"
              data-testid="context-usage-badge-slot"
            >
              <ContextUsageBadge
                usage={contextUsage}
                onOpenDetail={() => setTokenDiagOpen(true)}
              />
            </div>
          ) : null}
          <form onSubmit={handleSend} className="os-composer-wrap">
            <div className="relative" ref={composerWrapRef}>
              <ComposerSlashPopup
                open={isSlashOpen}
                query={slashQuery}
                items={filteredSlashItems}
                selectedIndex={slashSelectedIndex}
                onSelectIndex={setSlashSelectedIndex}
                onSelectItem={handleSelectSlashItem}
                recentIds={recentSlashIds}
              />
              <div className="os-composer-row">
              <div
                className={`os-composer ${
                  replyTarget || pendingAttachments.length > 0 || queued.rows.length > 0
                    ? 'flex-col items-stretch !rounded-2xl !p-2'
                    : ''
                } ${replyTarget ? 'os-composer--reply' : ''} ${
                  queued.rows.length > 0 ? 'os-composer--queued' : ''
                } ${composerDragOver ? 'os-composer--drag-over' : ''}`}
                onDragEnter={handleComposerDragEnter}
                onDragOver={handleComposerDragOver}
                onDragLeave={handleComposerDragLeave}
                onDrop={handleComposerDrop}
              >
                {/* #925: the queued pane mounts INSIDE .os-composer at the very
                    top, extending directly out of the message input box above
                    the reply and attachment preview strips. */}
                <QueuedSendPane
                  rows={queued.rows}
                  maxHeightPx={queuedPaneMaxHeightPx(transcriptHeightPx)}
                  onChangeText={queued.update}
                  onDelete={queued.remove}
                  onClearAll={queued.clearAll}
                  onHoldIdsChange={setQueuedHoldIds}
                  interruptible={
                    status === 'open' && queued.rows.length > 0 && generationIsInFlight(messages, awaitingAssistant)
                  }
                />
                {replyTarget && (
                  <div
                    className="flex items-center justify-between gap-2 px-2.5 py-1 text-xs text-base-content/70 border-b border-base-content/10 mb-1 w-full"
                    data-testid="composer-reply-strip"
                  >
                    <div className="flex items-center gap-1.5 min-w-0 flex-1">
                      <Reply className="h-3.5 w-3.5 shrink-0 opacity-70" aria-hidden="true" />
                      <span className="truncate" title={replyTarget.text}>
                        {replyTarget.speaker ? (
                          <strong className="font-semibold text-base-content/90 mr-1">
                            {replyTarget.speaker}:
                          </strong>
                        ) : null}
                        <span className="opacity-75">
                          {replyTarget.text.replace(/\s+/g, ' ').slice(0, 100)}
                        </span>
                      </span>
                    </div>
                    <button
                      type="button"
                      className="btn btn-ghost btn-xs btn-circle h-5 w-5 min-h-0 text-base-content/60 hover:text-base-content"
                      aria-label="Dismiss reply"
                      data-testid="dismiss-reply-button"
                      onClick={() => setReplyTarget(null)}
                    >
                      ×
                    </button>
                  </div>
                )}
                <ComposerAttachChips
                  attachments={pendingAttachments}
                  onRemove={removeAttachment}
                />
                <div className={`flex items-center gap-1.5 min-h-0 ${replyTarget || pendingAttachments.length > 0 || queued.rows.length > 0 ? 'w-full' : 'flex-1'}`}>
                  <div className="relative" ref={plusRef}>
                    <input
                      ref={fileInputRef}
                      type="file"
                      multiple
                      className="hidden"
                      data-testid="composer-file-input"
                      aria-hidden="true"
                      tabIndex={-1}
                      onChange={(event) => {
                        enqueueComposerFiles(filesFromList(event.target.files))
                        event.target.value = ''
                      }}
                    />
                    <button
                      type="button"
                      className="os-composer__icon"
                      aria-label="Add"
                      aria-haspopup="menu"
                      aria-expanded={plusOpen}
                      data-testid="composer-plus-button"
                      onClick={() => setPlusOpen((value: boolean) => !value)}
                    >
                      <Plus className="h-4 w-4" aria-hidden="true" />
                    </button>
                    {plusOpen && !pluginsPanelOpen && (
                      <ul
                        role="menu"
                        aria-label="Chat actions"
                        className="os-plus-menu"
                      >
                        <li role="none">
                          <button
                            type="button"
                            role="menuitem"
                            aria-disabled={!composerMenu?.addFiles?.enabled}
                            className={`os-plus-menu__item ${
                              !composerMenu?.addFiles?.enabled ? 'opacity-60 cursor-not-allowed' : ''
                            }`}
                            title={
                              composerMenu?.addFiles?.enabled
                                ? 'Add files to this chat'
                                : composerMenu?.addFiles?.reason
                            }
                            onClick={() => {
                              if (!composerMenu?.addFiles?.enabled) {
                                addToast({
                                  type: 'info',
                                  title: 'Add files',
                                  message: `${composerMenu?.addFiles?.reason || 'File attachments are unavailable'}. Switch to an API agent to attach.`,
                                })
                                setPlusOpen(false)
                                return
                              }
                              setPlusOpen(false)
                              fileInputRef.current?.click()
                            }}
                          >
                            <Paperclip className="h-4 w-4" aria-hidden="true" />
                            Add files
                          </button>
                        </li>
                        <li role="none">
                          <button
                            type="button"
                            role="menuitem"
                            // #550: Compact summarises server-side history, so a
                            // CLI/remote seat has nothing for it to act on. Kept
                            // visible-but-disabled with the reason (the same read
                            // `Add files` uses one item above, and #511's
                            // precedent) rather than vanishing silently.
                            // #636: CLI seats now light up when a default API is
                            // configured or the provider declares cli_compact; a
                            // greyed CLI item's hover says the API is missing.
                            data-testid="composer-compact-button"
                            aria-disabled={!composerMenu?.compact?.enabled}
                            className={`os-plus-menu__item ${
                              !composerMenu?.compact?.enabled ? 'opacity-60 cursor-not-allowed' : ''
                            }`}
                            title={
                              composerMenu?.compact?.enabled
                                ? 'Summarise this conversation and reclaim context'
                                : composerMenu?.compact?.reason
                            }
                            onClick={() => {
                              if (!composerMenu?.compact?.enabled) {
                                addToast({
                                  type: 'info',
                                  title: 'Compact',
                                  message: composerMenu?.compact?.reason || 'Compact is unavailable',
                                })
                                setPlusOpen(false)
                                return
                              }
                              void handleCompact()
                            }}
                          >
                            <Layers className="h-4 w-4" aria-hidden="true" />
                            Compact
                          </button>
                        </li>
                        <li role="none">
                          <button
                            type="button"
                            role="menuitem"
                            // #516: Plugins ride the swarm-owned gate (#511) —
                            // visible-but-disabled with the reason on CLI/remote
                            // seats, opening the per-agent panel on swarm seats.
                            data-testid="composer-plugins-button"
                            aria-disabled={!composerMenu?.plugins?.enabled}
                            aria-haspopup="menu"
                            className={`os-plus-menu__item ${
                              !composerMenu?.plugins?.enabled ? 'opacity-60 cursor-not-allowed' : ''
                            }`}
                            title={
                              composerMenu?.plugins?.enabled
                                ? 'Toggle this agent’s plugins'
                                : composerMenu?.plugins?.reason
                            }
                            onClick={() => {
                              if (!composerMenu?.plugins?.enabled) {
                                addToast({
                                  type: 'info',
                                  title: 'Plugins',
                                  message: composerMenu?.plugins?.reason || 'Plugins are unavailable',
                                })
                                setPlusOpen(false)
                                return
                              }
                              setPluginsPanelOpen(true)
                            }}
                          >
                            <Plug className="h-4 w-4" aria-hidden="true" />
                            Plugins
                          </button>
                        </li>
                        <li role="none">
                          <button
                            type="button"
                            role="menuitem"
                            data-testid="composer-enhance-button"
                            aria-label="Rewrite prompt with AI"
                            aria-disabled={enhancing || !input?.trim()}
                            className={`os-plus-menu__item ${
                              enhancing || !input?.trim() ? 'opacity-60 cursor-not-allowed' : ''
                            }`}
                            title={
                              !input?.trim()
                                ? 'Enter a draft prompt to rewrite with AI'
                                : 'Rewrite this draft with AI (✨)'
                            }
                            onClick={() => {
                              if (!input?.trim()) {
                                addToast({
                                  type: 'info',
                                  title: 'Rewrite prompt',
                                  message: 'Enter a draft prompt in the composer to rewrite with AI.',
                                })
                                setPlusOpen(false)
                                return
                              }
                              void handleEnhance()
                            }}
                          >
                            <SparklesIcon className={`h-4 w-4 ${enhancing ? 'animate-pulse' : ''}`} aria-hidden="true" />
                            Rewrite prompt with AI
                          </button>
                        </li>
                      </ul>
                    )}
                    {plusOpen && pluginsPanelOpen && <ComposerPluginsPanel onClose={() => setPlusOpen(false)} />}
                  </div>
                  {/* #858/#860/#1069: API seats get the enhanced composer — inline
                      ghost-text autocomplete. (The prompt rewrite action previously
                      embedded inside the input has been moved to the + menu). Other kinds
                      keep the plain textarea (autocomplete is API-model backed; CLI/remote
                      input would need per-provider wiring). */}
                  {isApiAgent ? (
                    <ChatMessageInput
                      textareaRef={composerRef}
                      value={input}
                      onApplyText={setInput}
                      agentId={selectedBlueprint || undefined}
                      conversationId={conversationId || undefined}
                      textareaProps={{
                        rows: 1,
                        className: 'os-composer__input',
                        placeholder: composerPlaceholder,
                        value: input,
                        onChange: handleInputChange,
                        onPaste: handleComposerPaste,
                        onKeyDown: handleComposerKeyDown,
                        'aria-label': 'Chat message',
                        'aria-haspopup': 'listbox',
                        'aria-expanded': isSlashOpen,
                        'aria-controls': isSlashOpen ? 'composer-slash-menu' : undefined,
                      }}
                    />
                  ) : (
                  <textarea
                    ref={composerRef}
                    rows={1}
                    className="os-composer__input"
                    placeholder={composerPlaceholder}
                    value={input}
                    onChange={handleInputChange}
                    onKeyDown={handleComposerKeyDown}
                    onPaste={handleComposerPaste}
                    aria-label="Chat message"
                    aria-haspopup="listbox"
                    aria-expanded={isSlashOpen}
                    aria-controls={isSlashOpen ? 'composer-slash-menu' : undefined}
                  />
                  )}
                  {/* #732: ONE permanently mounted slot — the kbd used to
                      mount/unmount with the draft, re-flowing the pill on the
                      first and last keystroke. The glyph swaps in place; the
                      node (and its reserved width) never changes. */}
                  <span className="os-composer__hint-slot" data-testid="composer-hint-slot">
                    {sendNowHint ? (
                      /* #631: the ↵ reveal exists ONLY to announce the interrupt-
                         send action while a queued send waits. No queue → no hint. */
                      <kbd
                        className="os-composer__hint kbd kbd-xs"
                        data-testid="composer-send-hint"
                        title="Send Now! ↵"
                      >
                        ↵
                      </kbd>
                    ) : input ? (
                      <kbd
                        className="os-composer__hint kbd kbd-xs"
                        data-testid="composer-clear-hint"
                        title="Esc to clear"
                      >
                        Esc
                      </kbd>
                    ) : (
                      <kbd
                        className="os-composer__hint kbd kbd-xs"
                        data-testid="composer-hint-placeholder"
                        title=""
                        aria-hidden="true"
                      >
                        ↵
                      </kbd>
                    )}
                  </span>
                  {renderRoutingPicker()}
                  <button
                    type="button"
                    className="os-composer__icon"
                    aria-label={sttListening ? 'Stop voice input' : 'Voice input'}
                    aria-pressed={sttListening}
                    data-testid="composer-mic"
                    data-stt-path={sttPathUsed ?? undefined}
                    onClick={handleMic}
                  >
                    <Mic className="h-4 w-4" aria-hidden="true" />
                  </button>
                  {sttPathUsed ? (
                    <span className="sr-only" data-testid="stt-path">
                      Voice input used {describeSpeechPath(sttPathUsed, 'stt')}
                    </span>
                  ) : null}
                </div>
                </div>{/* /os-composer */}
                {/* #632: the primary action lives OUTSIDE the input box, to its
                    right. Idle: send (↑) when there is a draft. Busy: square
                    stop (□) — and the send stays beside it when a draft is
                    typed, because clicking Send mid-flight is exactly how a
                    send gets QUEUED (#603); removing it would kill queueing.
                    The mic stays inside the input regardless. */}
                {composerBusy ? (
                  <button
                    type="button"
                    className="os-composer__send os-composer__send--stop"
                    aria-label="Stop generating"
                    title="Stop the generation in flight (queued sends stay queued)"
                    data-testid="composer-stop"
                    onClick={interruptRunningTurn}
                  >
                    <Square className="h-3.5 w-3.5 fill-current" aria-hidden="true" />
                  </button>
                ) : null}
                {hasSendableDraft ? (
                  <button
                    type="submit"
                    className="os-composer__send"
                    aria-label="Send"
                  >
                    <ArrowUp className="h-4 w-4" strokeWidth={2.5} aria-hidden="true" />
                  </button>
                ) : null}
              </div>{/* /os-composer-row */}
            </div>
          </form>
        </div>

    </>
  )
}
