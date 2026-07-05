const GRID_PADDING = 4;
const MIN_GRID_SIZE = 13;

const elements = {
    customForm: document.querySelector("#custom-game-form"),
    customLetters: document.querySelector("#custom-letters"),
    randomButton: document.querySelector("#random-game-button"),
    status: document.querySelector("#board-status"),
    boardWrap: document.querySelector(".board-wrap"),
    grid: document.querySelector("#grid"),
    gameId: document.querySelector("#game-id"),
    copyGameIdButton: document.querySelector("#copy-game-id-button"),
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
    dragged: null,
    expandedWord: null,
    definitionCache: new Map(),
};

function emitAction(eventName, payload = {}) {
    return new Promise((resolve) => {
        if (!ui.socket || !ui.socket.connected) {
            renderMessage("Connection is not ready yet.");
            resolve({ success: false, message: "Connection is not ready yet." });
            return;
        }

        ui.socket.emit(eventName, payload, (response = { success: true }) => {
            resolve(response);
        });
    });
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
    for (const detail of ui.state.formed_words) {
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

function render(state) {
    ui.state = state;
    renderSession();
    renderStatus();
    renderRack();
    renderWords();
    renderMessages();
    renderGrid();
}

function renderSession() {
    const gameId = ui.state.game_id || ui.gameId || "";
    ui.gameId = gameId || null;
    elements.gameId.value = gameId;
    elements.copyGameIdButton.disabled = !gameId;
}

function renderMessage(message) {
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
    elements.status.classList.toggle("valid", ui.state.is_valid && !ui.state.is_game_over);
    elements.status.classList.toggle("invalid", !ui.state.is_valid);
    elements.status.classList.toggle("complete", ui.state.is_game_over);
    elements.status.textContent = ui.state.is_game_over
        ? "Complete"
        : ui.state.is_valid ? "Valid" : "Invalid";
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

async function copyGameId() {
    const gameId = elements.gameId.value;
    if (!gameId) {
        return;
    }

    elements.gameId.select();
    elements.gameId.setSelectionRange(0, gameId.length);

    try {
        if (navigator.clipboard && navigator.clipboard.writeText) {
            await navigator.clipboard.writeText(gameId);
        } else {
            document.execCommand("copy");
        }
        renderMessage("Game ID copied.");
    } catch (error) {
        renderMessage("Select the Game ID and copy it.");
    }
}

function renderWords() {
    elements.wordList.innerHTML = "";

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
    messages.push(...ui.state.messages);

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
    if (!covered) {
        tileElement.classList.add("orphan");
    } else if (covered.invalid) {
        tileElement.classList.add("invalid");
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

elements.customForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    ui.selected = { x: 0, y: 0 };
    await emitAction("create_game", {
        mode: "custom",
        letters: elements.customLetters.value,
    });
});

elements.randomButton.addEventListener("click", async () => {
    ui.selected = { x: 0, y: 0 };
    await emitAction("create_game", { mode: "random" });
});

elements.peelButton.addEventListener("click", peel);
elements.copyGameIdButton.addEventListener("click", copyGameId);

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
    const activeTag = document.activeElement && document.activeElement.tagName;
    if (activeTag === "INPUT" || activeTag === "TEXTAREA") {
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
    ui.socket.on("connect", () => {
        const params = new URLSearchParams(window.location.search);
        const gameId = params.get("game");
        if (gameId) {
            emitAction("join_game", { game_id: gameId });
        } else {
            emitAction("create_game", { mode: "random" });
        }
    });
    ui.socket.on("joined_game", (data) => {
        ui.gameId = data.game_id;
        ui.playerId = data.player_id;
    });
    ui.socket.on("state", render);
    ui.socket.on("action_error", (data) => {
        renderMessage(data.message || "Action failed.");
    });
}

initializeSocket();
