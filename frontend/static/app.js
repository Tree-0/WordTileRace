const GRID_PADDING = 4;
const MIN_GRID_SIZE = 13;
const SESSION_STORAGE_KEY = "wordTileRaceSession";

const SOCKET_TIMING_DEBUG =
    new URLSearchParams(window.location.search).has("debugTiming") ||
    window.localStorage.getItem("debugTiming") === "1";

let copyFeedbackTimeout = null;

const elements = {
    homeView: document.querySelector("#home-view"),
    gameView: document.querySelector("#game-view"),
    customForm: document.querySelector("#custom-game-form"),
    customLetters: document.querySelector("#custom-letters"),
    bagMultiplierChoices: document.querySelectorAll('[name="bag_multiplier_choice"]'),
    customBagMultiplierWrap: document.querySelector("#custom-bag-multiplier-wrap"),
    customBagMultiplier: document.querySelector("#custom-bag-multiplier"),
    randomButton: document.querySelector("#random-game-button"),
    settingsToggle: document.querySelector("#settings-toggle"),
    newGameSettings: document.querySelector("#new-game-settings"),
    joinForm: document.querySelector("#join-game-form"),
    joinInput: document.querySelector("#join-game-input"),
    nicknameInput: document.querySelector("#nickname-input"),
    lobbyStatus: document.querySelector("#lobby-status"),
    playersDrawer: document.querySelector("#players-drawer"),
    playersToggle: document.querySelector("#players-toggle"),
    playersPanel: document.querySelector("#players-panel"),
    playersCount: document.querySelector("#players-count"),
    playersList: document.querySelector("#players-list"),
    helpDialog: document.querySelector("#help-dialog"),
    winnerDialog: document.querySelector("#winner-dialog"),
    winnerMessage: document.querySelector("#winner-message"),
    status: document.querySelector("#board-status"),
    boardWrap: document.querySelector(".board-wrap"),
    grid: document.querySelector("#grid"),
    gameId: document.querySelector("#game-id"),
    copyGameLinkButton: document.querySelector("#copy-game-link-button"),
    rack: document.querySelector("#rack"),
    rackCount: document.querySelector("#rack-count"),
    bagCount: document.querySelector("#bag-count"),
    peelButton: document.querySelector("#peel-button"),
    wordList: document.querySelector("#word-list"),
    messages: document.querySelector("#messages"),
};

const ui = {
    selected: { x: 0, y: 0 },
    state: null,
    socket: null,
    gameId: null,
    playerId: null,
    playerName: null,
    pendingPlayerName: null,
    inviteUrl: null,
    dragged: null,
    expandedWord: null,
    definitionCache: new Map(),
    pendingActions: new Map(),
    dismissedWinner: null,
};

function emitAction(eventName, payload = {}) {
    return new Promise((resolve) => {
        if (!ui.socket || !ui.socket.connected) {
            renderMessage("Connection is not ready yet.");
            resolve({ success: false, message: "Connection is not ready yet." });
            return;
        }

        const actionId = createActionId(eventName);
        const sentAt = performance.now();
        const debugPayload = {
            ...payload,
            _client_action_id: actionId,
            _client_sent_at_ms: Date.now(),
        };
        ui.pendingActions.set(actionId, {
            eventName,
            sentAt,
            wallSentAt: debugPayload._client_sent_at_ms,
        });
        logSocketTiming("emit", {
            action: eventName,
            client_action_id: actionId,
            payload,
        });

        ui.socket.emit(eventName, debugPayload, (response = { success: true }) => {
            logIncomingTiming("ack", response, eventName);
            resolve(response);
        });
    });
}

function createActionId(eventName) {
    const random = Math.random().toString(36).slice(2, 8);
    return `${eventName}-${Date.now()}-${random}`;
}

function logSocketTiming(label, details) {
    if (!SOCKET_TIMING_DEBUG) {
        return;
    }
    console.log(`[socket timing] ${label}`, details);
}

function logIncomingTiming(eventName, payload, fallbackAction = null) {
    const timing = payload && payload.debug_timing;
    if (!timing) {
        return;
    }

    const pending = ui.pendingActions.get(timing.client_action_id);
    const receivedAt = performance.now();
    logSocketTiming(eventName, {
        action: timing.action || fallbackAction,
        client_action_id: timing.client_action_id,
        event: eventName,
        response_type: payload.type || null,
        success: payload.success,
        client_emit_to_receive_ms: pending
            ? roundTiming(receivedAt - pending.sentAt)
            : null,
        client_to_server_receive_ms_approx: timing.client_sent_at_ms
            ? roundTiming(timing.server_received_at_ms - timing.client_sent_at_ms)
            : null,
        server_process_ms: timing.server_process_ms,
        server_steps_ms: timing.server_steps_ms || {},
        server_received_at: new Date(timing.server_received_at_ms).toISOString(),
    });

    if (eventName === "ack" || eventName === "action_error") {
        window.setTimeout(() => {
            ui.pendingActions.delete(timing.client_action_id);
        }, 5000);
    }
}

function logRenderTiming(eventName, payload, startedAt) {
    const timing = payload && payload.debug_timing;
    if (!timing) {
        return;
    }

    logSocketTiming("render", {
        action: timing.action,
        client_action_id: timing.client_action_id,
        source_event: eventName,
        render_ms: roundTiming(performance.now() - startedAt),
    });
}

function roundTiming(value) {
    return Math.round(value * 10) / 10;
}

function savedSession() {
    try {
        const value = window.localStorage.getItem(SESSION_STORAGE_KEY);
        return value ? JSON.parse(value) : null;
    } catch (error) {
        return null;
    }
}

function saveSession(gameId, playerId, playerName = null) {
    if (!gameId || !playerId) {
        return;
    }
    try {
        window.localStorage.setItem(
            SESSION_STORAGE_KEY,
            JSON.stringify({ gameId, playerId, playerName }),
        );
    } catch (error) {
        // Local storage can be disabled; reconnect will simply be manual.
    }
}

function inviteUrl(gameId) {
    if (!gameId) {
        return "";
    }
    const url = new URL(window.location.href);
    url.search = "";
    url.hash = "";
    url.searchParams.set("game", gameId);
    return url.toString();
}

function gameIdFromInput(value) {
    const trimmed = String(value || "").trim();
    if (!trimmed) {
        return null;
    }

    try {
        const url = new URL(trimmed, window.location.href);
        const linkedGameId = url.searchParams.get("game");
        if (linkedGameId && linkedGameId.trim()) {
            return linkedGameId.trim();
        }
    } catch (error) {
        // Malformed links fall through to the raw-ID check below.
    }

    const looksLikeLink = /^(?:https?:\/\/|\/|\?)/i.test(trimmed);
    return looksLikeLink ? null : trimmed;
}

function setLobbyMessage(message, pending = false) {
    elements.lobbyStatus.textContent = message;
    elements.lobbyStatus.classList.toggle("pending", pending);
    elements.lobbyStatus.hidden = !message;
}

function clearLobbyMessage() {
    setLobbyMessage("");
}

function requiredPlayerName() {
    const playerName = elements.nicknameInput.value.trim().replace(/\s+/g, " ");
    if (!playerName) {
        setLobbyMessage("Choose a nickname before entering a match.");
        elements.nicknameInput.focus();
        return null;
    }

    elements.nicknameInput.value = playerName;
    return playerName;
}

function showGameView(gameId) {
    elements.homeView.hidden = true;
    elements.gameView.hidden = false;
    clearLobbyMessage();

    if (gameId) {
        const url = new URL(window.location.href);
        url.search = "";
        url.hash = "";
        url.searchParams.set("game", gameId);
        window.history.replaceState({}, "", url);
    }
}

function setSettingsOpen(isOpen) {
    elements.newGameSettings.hidden = !isOpen;
    elements.settingsToggle.setAttribute("aria-expanded", String(isOpen));
    elements.settingsToggle.textContent = isOpen ? "Hide custom rules" : "Custom rules";
    if (isOpen) {
        elements.customLetters.focus();
    }
}

function selectedBagMultiplier() {
    const selected = Array.from(elements.bagMultiplierChoices).find(
        (choice) => choice.checked,
    );
    if (!selected || selected.value !== "custom") {
        return Number(selected?.value || 1);
    }

    const entered = Number(elements.customBagMultiplier.value);
    if (!Number.isFinite(entered) || entered < 1) {
        setLobbyMessage("Enter a custom bag multiplier between 1x and 4x.");
        elements.customBagMultiplier.focus();
        return null;
    }

    const normalized = Math.min(4, Math.trunc(entered * 10) / 10);
    elements.customBagMultiplier.value = normalized.toFixed(1);
    return normalized;
}

function updateCustomBagMultiplier() {
    const selected = Array.from(elements.bagMultiplierChoices).find(
        (choice) => choice.checked,
    );
    const isCustom = selected?.value === "custom";
    const rackIsRequired = selected?.value === "0";
    elements.customBagMultiplierWrap.hidden = !isCustom;
    elements.customBagMultiplier.required = isCustom;
    elements.customLetters.setAttribute("aria-required", String(rackIsRequired));
}

function setPlayersOpen(isOpen) {
    elements.playersDrawer.classList.toggle("open", isOpen);
    elements.playersToggle.setAttribute("aria-expanded", String(isOpen));
    elements.playersPanel.setAttribute("aria-hidden", String(!isOpen));
}

function openDialog(dialog) {
    if (!dialog || dialog.open) {
        return;
    }
    if (typeof dialog.showModal === "function") {
        dialog.showModal();
    } else {
        dialog.setAttribute("open", "");
    }
}

function closeDialog(dialog) {
    if (!dialog || !dialog.open) {
        return;
    }
    if (typeof dialog.close === "function") {
        dialog.close();
    } else {
        dialog.removeAttribute("open");
    }
}

async function requestJson(path) {
    const response = await fetch(path);
    return response.json();
}

function pointKey(x, y) {
    return `${x},${y}`;
}

function tileMap() {
    const map = new Map();
    for (const tile of ui.state.placed_tiles) {
        map.set(pointKey(tile.x, tile.y), tile);
    }
    return map;
}

function wordCoverage() {
    const coverage = new Map();
    for (const detail of ui.state.formed_words || []) {
        for (const point of detail.points) {
            const key = pointKey(point.x, point.y);
            const previous = coverage.get(key);
            coverage.set(key, {
                valid: detail.is_valid && (!previous || previous.valid),
                invalid: !detail.is_valid || Boolean(previous && previous.invalid),
            });
        }
    }
    return coverage;
}

function viewportBounds() {
    const points = ui.state.placed_tiles.map((tile) => ({ x: tile.x, y: tile.y }));
    points.push(ui.selected);

    let minX = Math.min(...points.map((point) => point.x)) - GRID_PADDING;
    let maxX = Math.max(...points.map((point) => point.x)) + GRID_PADDING;
    let minY = Math.min(...points.map((point) => point.y)) - GRID_PADDING;
    let maxY = Math.max(...points.map((point) => point.y)) + GRID_PADDING;

    const width = maxX - minX + 1;
    if (width < MIN_GRID_SIZE) {
        const extra = MIN_GRID_SIZE - width;
        minX -= Math.floor(extra / 2);
        maxX += Math.ceil(extra / 2);
    }

    const height = maxY - minY + 1;
    if (height < MIN_GRID_SIZE) {
        const extra = MIN_GRID_SIZE - height;
        minY -= Math.floor(extra / 2);
        maxY += Math.ceil(extra / 2);
    }

    return { minX, maxX, minY, maxY };
}

function normalizedState(state) {
    return {
        ...state,
        rack: state.rack || {},
        placed_tiles: state.placed_tiles || [],
        formed_words: state.formed_words || [],
        messages: state.messages || [],
        players: state.players || state.public?.players || [],
    };
}

function render(state) {
    ui.state = normalizedState(state);
    ui.playerId = ui.state.player_id || ui.playerId;
    ui.playerName = ui.state.player_name || ui.playerName;
    renderSession();
    renderStatus();
    renderPlayers();
    renderRack();
    renderWords();
    renderMessages();
    renderGrid();
    renderWinnerAnnouncement();
}

function applyStateDiff(diff) {
    if (!ui.state) {
        if (diff.message) {
            renderMessage(diff.message);
        }
        return;
    }

    if (diff.success === false) {
        renderMessage(diff.message || "Action failed.");
        return;
    }

    const state = normalizedState({
        ...ui.state,
        rack: { ...ui.state.rack },
        placed_tiles: ui.state.placed_tiles.map((tile) => ({ ...tile })),
        messages: [...(ui.state.messages || [])],
    });

    if (diff.type === "tile_placed") {
        setPlacedTile(state, diff.point, diff.tile);
        applyRackDelta(state, diff.rack_delta);
        updateActionFlags(state, diff);
        updateChangedWordValidation(state, diff);
    } else if (diff.type === "tile_moved") {
        removePlacedTile(state, diff.from);
        setPlacedTile(state, diff.to, diff.tile);
        updateActionFlags(state, diff);
        updateChangedWordValidation(state, diff);
    } else if (diff.type === "tile_removed") {
        removePlacedTile(state, diff.point);
        applyRackDelta(state, diff.rack_delta);
        updateActionFlags(state, diff);
        updateChangedWordValidation(state, diff);
    } else if (diff.type === "rack_changed" || diff.type === "peeled") {
        applyRackDelta(state, diff.rack_delta);
        if (typeof diff.bag_count === "number") {
            state.bag_count = diff.bag_count;
        }
        if (diff.validated_board) {
            applyValidatedBoard(state, diff.validated_board);
        }
        if (typeof diff.validation_stale === "boolean") {
            state.validation_stale = diff.validation_stale;
        }
        if (typeof diff.is_valid === "boolean") {
            state.is_valid = diff.is_valid;
        }
        updateActionFlags(state, diff);
        if (diff.message) {
            state.message = diff.message;
            state.messages = [diff.message];
        }
    } else if (diff.type === "game_over") {
        state.is_game_over = true;
        state.winner_id = diff.winner_id;
        state.winner_name = diff.winner_name;
        state.bag_count = diff.bag_count;
        state.can_peel = false;
        state.can_dump = false;
        state.validation_stale = false;
        if (diff.validated_board) {
            applyValidatedBoard(state, diff.validated_board);
        }
        state.message = diff.message || `${winnerDisplayName(state)} wins!`;
        state.messages = [state.message];
    }

    render(state);
}

function applyPublicState(publicState) {
    if (!ui.state || !publicState) {
        return;
    }

    const state = { ...ui.state };
    for (const field of [
        "bag_count",
        "is_game_over",
        "winner_id",
        "winner_name",
        "mode",
    ]) {
        if (Object.hasOwn(publicState, field)) {
            state[field] = publicState[field];
        }
    }
    if (Array.isArray(publicState.players)) {
        state.players = publicState.players;
    }

    ui.state = normalizedState(state);
    elements.bagCount.textContent = ui.state.bag_count;
    renderPlayers();
    renderStatus();
    renderWinnerAnnouncement();
}

function applyPublicStateDiff(diff) {
    if (!ui.state || !diff) {
        return;
    }

    if (diff.type === "player_changed" && diff.player) {
        const players = [...ui.state.players];
        const index = players.findIndex((player) =>
            player.player_id === diff.player.player_id
        );
        if (index >= 0) {
            players[index] = diff.player;
        } else {
            players.push(diff.player);
        }
        applyPublicState({ ...diff, players });
        return;
    }

    applyPublicState(diff);
}

function setPlacedTile(state, point, tile) {
    removePlacedTile(state, point);
    state.placed_tiles.push({
        x: point.x,
        y: point.y,
        char: tile.char,
        is_wildcard: Boolean(tile.is_wildcard),
    });
}

function removePlacedTile(state, point) {
    state.placed_tiles = state.placed_tiles.filter((tile) =>
        tile.x !== point.x || tile.y !== point.y
    );
}

function applyRackDelta(state, rackDelta = {}) {
    for (const [char, count] of Object.entries(rackDelta)) {
        const nextCount = (state.rack[char] || 0) + Number(count);
        if (nextCount > 0) {
            state.rack[char] = nextCount;
        } else {
            delete state.rack[char];
        }
    }
    state.rack_count = Object.values(state.rack).reduce((sum, count) => sum + count, 0);
}

function updateActionFlags(state, diff) {
    if (typeof diff.can_dump === "boolean") {
        state.can_dump = diff.can_dump;
    }
    if (typeof diff.can_peel === "boolean") {
        state.can_peel = diff.can_peel;
    }
}

function updateChangedWordValidation(state, diff) {
    if (diff.partial_validation) {
        applyPartialValidation(state, diff.partial_validation);
        return;
    }

    markValidationStale(state, diff.message);
}

function applyPartialValidation(state, partialValidation) {
    const changed = new Set(
        (
            partialValidation.changed_points ||
            partialValidation.affected_points ||
            []
        ).map((point) =>
            pointKey(point.x, point.y)
        )
    );
    const affectedWordPoints = new Map();
    for (const detail of partialValidation.formed_words || []) {
        const points = affectedWordPoints.get(detail.direction) || new Set();
        for (const point of detail.points) {
            points.add(pointKey(point.x, point.y));
        }
        affectedWordPoints.set(detail.direction, points);
    }

    const nextWords = state.formed_words.filter((detail) =>
        !wordTouchesChangedOrReplacedSegment(detail, changed, affectedWordPoints)
    );
    const existing = new Set(nextWords.map(wordSignature));

    for (const detail of partialValidation.formed_words || []) {
        const signature = wordSignature(detail);
        if (!existing.has(signature)) {
            nextWords.push(detail);
            existing.add(signature);
        }
    }

    state.formed_words = nextWords;
    state.validation_stale = true;
    state.is_valid = false;

    const invalidWords = nextWords
        .filter((detail) => !detail.is_valid)
        .map((detail) => detail.word);
    if (invalidWords.length > 0) {
        state.message = `Invalid known words: ${[...new Set(invalidWords)].sort().join(", ")}.`;
    } else if (nextWords.length > 0) {
        state.message = "Changed words checked. Peel will validate the whole board.";
    } else {
        state.message = "No complete words are known yet.";
    }
    state.messages = [state.message];
}

function wordTouchesChangedOrReplacedSegment(detail, changed, affectedWordPoints) {
    if (detail.points.some((point) => changed.has(pointKey(point.x, point.y)))) {
        return true;
    }

    const replacedPoints = affectedWordPoints.get(detail.direction);
    if (!replacedPoints) {
        return false;
    }

    return detail.points.some((point) => replacedPoints.has(pointKey(point.x, point.y)));
}

function applyValidatedBoard(state, boardState) {
    state.rack = { ...(boardState.rack || {}) };
    state.rack_count = Object.values(state.rack).reduce((sum, count) => sum + count, 0);
    state.placed_tiles = (boardState.placed_tiles || []).map((tile) => ({ ...tile }));
    state.formed_words = (boardState.formed_words || []).map((detail) => ({
        ...detail,
        points: detail.points.map((point) => ({ ...point })),
    }));
    state.is_valid = Boolean(boardState.is_valid);
    state.validation_stale = false;
}

function wordSignature(detail) {
    const points = detail.points
        .map((point) => pointKey(point.x, point.y))
        .sort()
        .join("|");
    return `${detail.direction}:${points}:${detail.word}`;
}

function markValidationStale(state, message) {
    state.validation_stale = true;
    state.is_valid = false;
    state.formed_words = [];
    state.message = message || "Board changed. Peel will validate before drawing.";
    state.messages = [state.message];
}

function renderSession() {
    const gameId = ui.state.game_id || ui.gameId || "";
    ui.gameId = gameId || null;
    elements.gameId.value = gameId;
    elements.copyGameLinkButton.disabled = !gameId;
    if (gameId && !ui.inviteUrl) {
        ui.inviteUrl = inviteUrl(gameId);
    }
}

function winnerDisplayName(state = ui.state) {
    if (!state) {
        return "A player";
    }
    if (state.winner_name) {
        return state.winner_name;
    }
    const winner = (state.players || []).find((player) =>
        player.player_id === state.winner_id
    );
    return winner?.player_name || "A player";
}

function renderPlayers() {
    const players = ui.state?.players || [];
    elements.playersCount.textContent = players.length;
    elements.playersList.innerHTML = "";

    if (players.length === 0) {
        const item = document.createElement("li");
        item.className = "empty-player-list";
        item.textContent = "Waiting for players...";
        elements.playersList.append(item);
        return;
    }

    for (const player of players) {
        const item = document.createElement("li");
        const isCurrentPlayer = player.player_id === ui.playerId;
        const isWinner = player.player_id === ui.state.winner_id;
        item.classList.toggle("current-player", isCurrentPlayer);
        item.classList.toggle("winner", isWinner);

        const name = document.createElement("span");
        name.className = "player-name";
        name.textContent = player.player_name || "Player";
        item.append(name);

        if (isCurrentPlayer) {
            const you = document.createElement("span");
            you.className = "player-you";
            you.textContent = "You";
            item.append(you);
        }

        const progress = document.createElement("span");
        progress.className = "player-progress";
        if (isWinner) {
            progress.textContent = "Winner";
        } else {
            const count = Number(player.rack_count) || 0;
            progress.textContent = `${count} tile${count === 1 ? "" : "s"} left`;
        }
        item.append(progress);
        elements.playersList.append(item);
    }
}

function renderWinnerAnnouncement() {
    if (!ui.state?.is_game_over) {
        return;
    }

    const winnerName = winnerDisplayName();
    const winnerKey = ui.state.winner_id || winnerName;
    if (ui.dismissedWinner === winnerKey || elements.winnerDialog.open) {
        return;
    }

    elements.winnerMessage.textContent = `${winnerName} wins!`;
    openDialog(elements.winnerDialog);
}

function renderMessage(message) {
    if (!elements.homeView.hidden) {
        setLobbyMessage(message);
        return;
    }

    if (!ui.state) {
        elements.status.classList.add("invalid");
        elements.status.textContent = "Disconnected";
        elements.messages.innerHTML = "";
        const item = document.createElement("li");
        item.textContent = message;
        elements.messages.append(item);
        return;
    }
    render({ ...ui.state, success: false, message });
}

function renderStatus() {
    const isStale = Boolean(ui.state.validation_stale) && !ui.state.is_game_over;
    const hasKnownWords = isStale && ui.state.formed_words.length > 0;
    elements.status.classList.toggle("stale", isStale);
    elements.status.classList.toggle("valid", ui.state.is_valid && !ui.state.is_game_over && !isStale);
    elements.status.classList.toggle("invalid", !ui.state.is_valid && !isStale);
    elements.status.classList.toggle("complete", ui.state.is_game_over);
    elements.status.textContent = ui.state.is_game_over
        ? `${winnerDisplayName()} wins`
        : hasKnownWords ? "Partial" : isStale ? "Unvalidated" : ui.state.is_valid ? "Valid" : "Invalid";
}

function renderRack() {
    elements.rack.innerHTML = "";

    const entries = Object.entries(ui.state.rack).sort(([a], [b]) => a.localeCompare(b));
    const total = entries.reduce((sum, [, count]) => sum + count, 0);
    elements.rackCount.textContent = total;
    elements.bagCount.textContent = ui.state.bag_count;
    elements.peelButton.disabled = !ui.state.can_peel;

    for (const [char, count] of entries) {
        const item = document.createElement("div");
        item.className = "rack-item";

        const tile = document.createElement("button");
        tile.type = "button";
        tile.className = "tile rack-tile";
        tile.draggable = true;
        tile.dataset.char = char;
        tile.innerHTML = `<span>${char}</span><span class="count">${count}</span>`;
        tile.addEventListener("click", () => placeSelected(char, true));
        tile.addEventListener("dragstart", () => {
            ui.dragged = { type: "rack", char };
        });

        const dumpButton = document.createElement("button");
        dumpButton.type = "button";
        dumpButton.className = "dump-button";
        dumpButton.textContent = "Dump";
        dumpButton.disabled = !ui.state.can_dump;
        dumpButton.addEventListener("click", (event) => {
            event.stopPropagation();
            dumpTile(char);
        });

        item.append(tile, dumpButton);
        elements.rack.append(item);
    }
}

async function copyGameLink() {
    const gameId = elements.gameId.value;
    if (!gameId) {
        return;
    }

    const text = inviteUrl(gameId);
    try {
        if (navigator.clipboard && navigator.clipboard.writeText) {
            await navigator.clipboard.writeText(text);
        } else {
            const textarea = document.createElement("textarea");
            textarea.value = text;
            textarea.setAttribute("readonly", "");
            textarea.style.position = "fixed";
            textarea.style.left = "-9999px";
            document.body.append(textarea);
            textarea.select();
            document.execCommand("copy");
            textarea.remove();
        }
        showCopyFeedback();
        renderMessage("Game link copied.");
    } catch (error) {
        renderMessage(`Could not copy automatically. Share this link: ${text}`);
    }
}

function showCopyFeedback() {
    window.clearTimeout(copyFeedbackTimeout);
    elements.copyGameLinkButton.textContent = "Copied!";
    elements.copyGameLinkButton.classList.add("copied");
    copyFeedbackTimeout = window.setTimeout(() => {
        elements.copyGameLinkButton.textContent = "Copy Game Link";
        elements.copyGameLinkButton.classList.remove("copied");
        copyFeedbackTimeout = null;
    }, 1800);
}

function renderWords() {
    elements.wordList.innerHTML = "";

    if (ui.state.validation_stale && ui.state.formed_words.length === 0) {
        ui.expandedWord = null;
        const item = document.createElement("li");
        item.textContent = "Unvalidated";
        elements.wordList.append(item);
        return;
    }

    if (ui.state.formed_words.length === 0) {
        ui.expandedWord = null;
        const item = document.createElement("li");
        item.textContent = "None";
        elements.wordList.append(item);
        return;
    }

    const visibleValidWords = new Set(
        ui.state.formed_words
            .filter((detail) => detail.is_valid)
            .map((detail) => detail.word)
    );
    if (ui.expandedWord && !visibleValidWords.has(ui.expandedWord)) {
        ui.expandedWord = null;
    }

    for (const detail of ui.state.formed_words) {
        const item = document.createElement("li");
        item.className = detail.is_valid ? "valid" : "invalid";
        const label = `${detail.word} ${detail.direction}`;

        if (!detail.is_valid) {
            item.textContent = label;
            elements.wordList.append(item);
            continue;
        }

        const button = document.createElement("button");
        button.type = "button";
        button.className = "word-button";
        button.textContent = label;
        button.setAttribute("aria-expanded", String(ui.expandedWord === detail.word));
        button.addEventListener("click", () => toggleWordDefinitions(detail.word));
        item.append(button);

        if (ui.expandedWord === detail.word) {
            item.append(renderWordDefinitions(detail.word));
        }

        elements.wordList.append(item);
    }
}

function renderWordDefinitions(word) {
    const container = document.createElement("div");
    container.className = "word-definitions";

    const cached = ui.definitionCache.get(word);
    if (!cached || cached.status === "loading") {
        container.classList.add("muted");
        container.textContent = "Loading definitions...";
        return container;
    }

    if (cached.status === "error") {
        container.classList.add("error");
        container.textContent = cached.message;
        return container;
    }

    if (cached.meanings.length === 0) {
        container.classList.add("muted");
        container.textContent = "No definitions found.";
        return container;
    }

    for (const meaning of cached.meanings) {
        const group = document.createElement("div");
        group.className = "definition-meaning";

        const partOfSpeech = document.createElement("div");
        partOfSpeech.className = "part-of-speech";
        partOfSpeech.textContent = meaning.part_of_speech;
        group.append(partOfSpeech);

        for (const definition of meaning.definitions) {
            const row = document.createElement("div");
            row.className = "definition-row";

            const definitionText = document.createElement("p");
            definitionText.textContent = definition.definition;
            row.append(definitionText);

            if (definition.example) {
                const example = document.createElement("p");
                example.className = "definition-example";
                example.textContent = definition.example;
                row.append(example);
            }

            group.append(row);
        }

        container.append(group);
    }

    return container;
}

async function toggleWordDefinitions(word) {
    if (ui.expandedWord === word) {
        ui.expandedWord = null;
        renderWords();
        return;
    }

    ui.expandedWord = word;
    if (ui.definitionCache.has(word)) {
        renderWords();
        return;
    }

    ui.definitionCache.set(word, { status: "loading" });
    renderWords();

    try {
        const data = await requestJson(`/api/definitions/${encodeURIComponent(word)}`);
        if (data.success) {
            ui.definitionCache.set(word, {
                status: "loaded",
                meanings: data.meanings || [],
            });
        } else {
            ui.definitionCache.set(word, {
                status: "error",
                message: data.message || "Definition lookup failed.",
            });
        }
    } catch (error) {
        ui.definitionCache.set(word, {
            status: "error",
            message: "Definition lookup failed.",
        });
    }

    if (ui.expandedWord === word) {
        renderWords();
    }
}

function renderMessages() {
    elements.messages.innerHTML = "";
    const messages = [];
    if (ui.state.message) {
        messages.push(ui.state.message);
    }
    for (const message of ui.state.messages || []) {
        if (!messages.includes(message)) {
            messages.push(message);
        }
    }

    for (const message of messages) {
        const item = document.createElement("li");
        item.textContent = message;
        elements.messages.append(item);
    }
}

function renderGrid() {
    const bounds = viewportBounds();
    const tiles = tileMap();
    const coverage = wordCoverage();
    const columns = bounds.maxX - bounds.minX + 1;

    elements.grid.innerHTML = "";
    elements.grid.style.gridTemplateColumns = `repeat(${columns}, var(--cell-size))`;

    for (let y = bounds.minY; y <= bounds.maxY; y += 1) {
        for (let x = bounds.minX; x <= bounds.maxX; x += 1) {
            elements.grid.append(renderCell(x, y, tiles, coverage));
        }
    }

    keepSelectedCellVisible();
}

function keepSelectedCellVisible() {
    const selectedCell = elements.grid.querySelector(".cell.selected");
    if (!selectedCell) {
        return;
    }

    const wrapRect = elements.boardWrap.getBoundingClientRect();
    const cellRect = selectedCell.getBoundingClientRect();
    const margin = Math.max(selectedCell.offsetWidth, selectedCell.offsetHeight);

    if (cellRect.left < wrapRect.left + margin) {
        elements.boardWrap.scrollLeft -= wrapRect.left + margin - cellRect.left;
    } else if (cellRect.right > wrapRect.right - margin) {
        elements.boardWrap.scrollLeft += cellRect.right - (wrapRect.right - margin);
    }

    if (cellRect.top < wrapRect.top + margin) {
        elements.boardWrap.scrollTop -= wrapRect.top + margin - cellRect.top;
    } else if (cellRect.bottom > wrapRect.bottom - margin) {
        elements.boardWrap.scrollTop += cellRect.bottom - (wrapRect.bottom - margin);
    }
}

function renderCell(x, y, tiles, coverage) {
    const cell = document.createElement("button");
    cell.type = "button";
    cell.className = "cell";
    cell.dataset.x = x;
    cell.dataset.y = y;

    if (x === ui.selected.x && y === ui.selected.y) {
        cell.classList.add("selected");
    }
    if (x === 0 && y === 0) {
        cell.classList.add("origin");
    }

    cell.addEventListener("click", () => {
        ui.selected = { x, y };
        renderGrid();
    });
    cell.addEventListener("dragover", (event) => event.preventDefault());
    cell.addEventListener("drop", (event) => {
        event.preventDefault();
        dropOnCell(x, y);
    });

    const tile = tiles.get(pointKey(x, y));
    if (tile) {
        cell.append(renderBoardTile(tile, x, y, coverage));
    }

    return cell;
}

function renderBoardTile(tile, x, y, coverage) {
    const tileElement = document.createElement("div");
    tileElement.className = "tile";
    tileElement.draggable = true;
    tileElement.textContent = tile.char;

    const key = pointKey(x, y);
    const covered = coverage.get(key);
    if (covered && covered.invalid) {
        tileElement.classList.add("invalid");
    } else if (covered && covered.valid) {
        tileElement.classList.add("valid");
    } else if (!covered && ui.state.is_valid) {
        tileElement.classList.add("valid");
    } else if (!covered) {
        tileElement.classList.add("orphan");
    } else {
        tileElement.classList.add("valid");
    }

    tileElement.addEventListener("dragstart", (event) => {
        event.stopPropagation();
        ui.dragged = { type: "board", from: { x, y } };
    });

    return tileElement;
}

async function dropOnCell(x, y) {
    ui.selected = { x, y };

    if (!ui.dragged || (ui.state && ui.state.is_game_over)) {
        return;
    }

    if (ui.dragged.type === "rack") {
        await emitAction("place_tile", {
            x,
            y,
            char: ui.dragged.char,
            overwrite: false,
        });
    }

    if (ui.dragged.type === "board") {
        await emitAction("move_tile", {
            from: ui.dragged.from,
            to: { x, y },
        });
    }

    ui.dragged = null;
}

async function placeSelected(char, overwrite) {
    if (ui.state && ui.state.is_game_over) {
        return;
    }

    await emitAction("place_tile", {
        x: ui.selected.x,
        y: ui.selected.y,
        char,
        overwrite,
    });
}

async function removeSelected() {
    if (ui.state && ui.state.is_game_over) {
        return;
    }

    await emitAction("remove_tile", ui.selected);
}

async function peel() {
    await emitAction("peel", {});
}

async function dumpTile(char) {
    await emitAction("dump", { char });
}

function selectedTile() {
    return ui.state?.placed_tiles.find((tile) =>
        tile.x === ui.selected.x && tile.y === ui.selected.y
    );
}

async function dumpSelectedTile() {
    if (!ui.state || ui.state.is_game_over || ui.state.bag_count <= 0) {
        return;
    }

    const tile = selectedTile();
    if (!tile) {
        return;
    }

    const char = tile.char;
    const point = { ...ui.selected };

    const removed = await emitAction("remove_tile", point);
    if (removed.success) {
        await dumpTile(char);
    }
}

elements.playersToggle.addEventListener("click", () => {
    setPlayersOpen(!elements.playersDrawer.classList.contains("open"));
});

for (const button of document.querySelectorAll("[data-open-help]")) {
    button.addEventListener("click", () => openDialog(elements.helpDialog));
}

for (const button of document.querySelectorAll("[data-close-dialog]")) {
    button.addEventListener("click", () => closeDialog(button.closest("dialog")));
}

for (const dialog of document.querySelectorAll("dialog")) {
    dialog.addEventListener("click", (event) => {
        if (event.target === dialog) {
            closeDialog(dialog);
        }
    });
}

elements.winnerDialog.addEventListener("close", () => {
    if (ui.state?.is_game_over) {
        ui.dismissedWinner = ui.state.winner_id || winnerDisplayName();
    }
});

elements.settingsToggle.addEventListener("click", () => {
    setSettingsOpen(elements.newGameSettings.hidden);
});

for (const choice of elements.bagMultiplierChoices) {
    choice.addEventListener("change", () => {
        updateCustomBagMultiplier();
        if (choice.checked && choice.value === "custom") {
            elements.customBagMultiplier.focus();
            elements.customBagMultiplier.select();
        }
    });
}
updateCustomBagMultiplier();

elements.customBagMultiplier.addEventListener("change", () => {
    const multiplier = selectedBagMultiplier();
    if (multiplier !== null) {
        clearLobbyMessage();
    }
});

elements.nicknameInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && elements.joinInput.value.trim()) {
        event.preventDefault();
        elements.joinForm.requestSubmit();
    }
});

elements.customForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const playerName = requiredPlayerName();
    if (!playerName) {
        return;
    }
    const bagMultiplier = selectedBagMultiplier();
    if (bagMultiplier === null) {
        return;
    }
    const customLetters = elements.customLetters.value.trim();
    if (bagMultiplier === 0 && !customLetters) {
        setLobbyMessage("Enter custom starting tiles when bag size is NONE.");
        elements.customLetters.focus();
        return;
    }
    ui.selected = { x: 0, y: 0 };
    ui.inviteUrl = null;
    ui.pendingPlayerName = playerName;
    setLobbyMessage("Creating custom match...", true);
    const response = await emitAction("create_game", {
        mode: "custom",
        letters: customLetters,
        bag_multiplier: bagMultiplier,
        player_name: playerName,
    });
    if (!response.success) {
        setLobbyMessage(response.message || "Could not create the match.");
    }
});

elements.randomButton.addEventListener("click", async () => {
    const playerName = requiredPlayerName();
    if (!playerName) {
        return;
    }
    ui.selected = { x: 0, y: 0 };
    ui.inviteUrl = null;
    ui.pendingPlayerName = playerName;
    setLobbyMessage("Creating match...", true);
    const response = await emitAction("create_game", {
        mode: "random",
        player_name: playerName,
    });
    if (!response.success) {
        setLobbyMessage(response.message || "Could not create the match.");
    }
});

elements.joinForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const playerName = requiredPlayerName();
    if (!playerName) {
        return;
    }
    const gameId = gameIdFromInput(elements.joinInput.value);
    if (!gameId) {
        setLobbyMessage("Enter a game ID or an invite link containing one.");
        return;
    }

    const saved = savedSession();
    ui.pendingPlayerName = playerName;
    setLobbyMessage("Joining match...", true);
    const response = await emitAction("join_game", {
        game_id: gameId,
        player_id: saved && saved.gameId === gameId ? saved.playerId : null,
        player_name: playerName,
    });
    if (!response.success) {
        setLobbyMessage(response.message || "Could not join the match.");
    }
});

elements.peelButton.addEventListener("click", peel);
elements.copyGameLinkButton.addEventListener("click", copyGameLink);

elements.rack.addEventListener("dragover", (event) => event.preventDefault());
elements.rack.addEventListener("drop", async (event) => {
    event.preventDefault();
    if (ui.dragged && ui.dragged.type === "board") {
        ui.selected = ui.dragged.from;
        await emitAction("remove_tile", ui.dragged.from);
    }
    ui.dragged = null;
});

document.addEventListener("dragend", () => {
    ui.dragged = null;
});

document.addEventListener("keydown", async (event) => {
    if (document.querySelector("dialog[open]") || elements.gameView.hidden) {
        return;
    }

    const activeTag = document.activeElement && document.activeElement.tagName;
    if (activeTag === "INPUT" || activeTag === "TEXTAREA") {
        return;
    }

    if (event.key === "Escape" && elements.playersDrawer.classList.contains("open")) {
        event.preventDefault();
        setPlayersOpen(false);
        elements.playersToggle.focus();
        return;
    }

    if (/^[a-z]$/i.test(event.key)) {
        event.preventDefault();
        await placeSelected(event.key.toUpperCase(), true);
        return;
    }

    if (event.key === "Backspace" || event.key === "Delete" || event.key === "Escape") {
        event.preventDefault();
        await removeSelected();
        return;
    }

    // Press space to peel a tile, when possible
    if (event.code === "Space") {
        event.preventDefault();
        // Press shift + space to dump the tile on the selected cell
        if (event.shiftKey) {
            await dumpSelectedTile();
        }
        else if (ui.state && ui.state.can_peel) {
            await peel();
        }
        return;
    }

    const moves = {
        ArrowUp: { x: 0, y: -1 },
        ArrowDown: { x: 0, y: 1 },
        ArrowLeft: { x: -1, y: 0 },
        ArrowRight: { x: 1, y: 0 },
    };
    const move = moves[event.key];
    if (move) {
        event.preventDefault();
        ui.selected = {
            x: ui.selected.x + move.x,
            y: ui.selected.y + move.y,
        };
        renderGrid();
    }
});

function initializeSocket() {
    if (!window.io) {
        renderMessage("Socket.IO client failed to load.");
        return;
    }

    ui.socket = window.io();
    ui.socket.on("connect", async () => {
        const params = new URLSearchParams(window.location.search);
        const gameId = params.get("game");
        const saved = savedSession();
        if (gameId) {
            elements.joinInput.value = gameId;
            if (
                saved
                && saved.gameId === gameId
                && saved.playerId
                && saved.playerName
            ) {
                ui.pendingPlayerName = saved.playerName || null;
                setLobbyMessage("Rejoining match...", true);
                const response = await emitAction("join_game", {
                    game_id: gameId,
                    player_id: saved.playerId,
                    player_name: saved.playerName || null,
                });
                if (!response.success) {
                    setLobbyMessage(response.message || "Could not join the match.");
                }
            } else {
                setLobbyMessage("Invite ready. Choose a nickname to join the match.", true);
                elements.nicknameInput.focus();
            }
        } else {
            clearLobbyMessage();
        }
    });
    ui.socket.on("joined_game", (data) => {
        logIncomingTiming("joined_game", data);
        ui.gameId = data.game_id;
        ui.playerId = data.player_id;
        ui.playerName = data.player_name || ui.pendingPlayerName;
        ui.inviteUrl = data.invite_url || inviteUrl(data.game_id);
        saveSession(ui.gameId, ui.playerId, ui.playerName);
        if (ui.playerName) {
            elements.nicknameInput.value = ui.playerName;
        }
        ui.pendingPlayerName = null;
        showGameView(ui.gameId);
    });
    ui.socket.on("state", (state) => {
        logIncomingTiming("state", state);
        const renderStartedAt = performance.now();
        render(state);
        logRenderTiming("state", state, renderStartedAt);
    });
    ui.socket.on("state_diff", (diff) => {
        logIncomingTiming("state_diff", diff);
        const renderStartedAt = performance.now();
        applyStateDiff(diff);
        logRenderTiming("state_diff", diff, renderStartedAt);
    });
    ui.socket.on("public_state", (state) => {
        applyPublicState(state);
    });
    ui.socket.on("public_state_diff", (diff) => {
        applyPublicStateDiff(diff);
    });
    ui.socket.on("action_error", (data) => {
        logIncomingTiming("action_error", data);
        renderMessage(data.message || "Action failed.");
    });
}

const initialSession = savedSession();
if (initialSession?.playerName) {
    elements.nicknameInput.value = initialSession.playerName;
}
const initialGameId = new URLSearchParams(window.location.search).get("game");
if (initialGameId) {
    elements.joinInput.value = initialGameId;
}

initializeSocket();
