const GRID_PADDING = 4;
const MIN_GRID_SIZE = 13;

const elements = {
    customForm: document.querySelector("#custom-game-form"),
    customLetters: document.querySelector("#custom-letters"),
    randomButton: document.querySelector("#random-game-button"),
    status: document.querySelector("#board-status"),
    boardWrap: document.querySelector(".board-wrap"),
    grid: document.querySelector("#grid"),
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
    dragged: null,
};

async function requestApi(path, payload = null) {
    const options = payload === null
        ? {}
        : {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        };

    const response = await fetch(path, options);
    const data = await response.json();
    render(data);
    return data;
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
    renderStatus();
    renderRack();
    renderWords();
    renderMessages();
    renderGrid();
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

function renderWords() {
    elements.wordList.innerHTML = "";

    if (ui.state.formed_words.length === 0) {
        const item = document.createElement("li");
        item.textContent = "None";
        elements.wordList.append(item);
        return;
    }

    for (const detail of ui.state.formed_words) {
        const item = document.createElement("li");
        item.className = detail.is_valid ? "valid" : "invalid";
        item.textContent = `${detail.word} ${detail.direction}`;
        elements.wordList.append(item);
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
        await requestApi("/api/place", {
            x,
            y,
            char: ui.dragged.char,
            overwrite: false,
        });
    }

    if (ui.dragged.type === "board") {
        await requestApi("/api/move", {
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

    await requestApi("/api/place", {
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

    await requestApi("/api/remove", ui.selected);
}

async function peel() {
    await requestApi("/api/peel", {});
}

async function dumpTile(char) {
    await requestApi("/api/dump", { char });
}

elements.customForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    ui.selected = { x: 0, y: 0 };
    await requestApi("/api/new", {
        mode: "custom",
        letters: elements.customLetters.value,
    });
});

elements.randomButton.addEventListener("click", async () => {
    ui.selected = { x: 0, y: 0 };
    await requestApi("/api/new", { mode: "random" });
});

elements.peelButton.addEventListener("click", peel);

elements.rack.addEventListener("dragover", (event) => event.preventDefault());
elements.rack.addEventListener("drop", async (event) => {
    event.preventDefault();
    if (ui.dragged && ui.dragged.type === "board") {
        ui.selected = ui.dragged.from;
        await requestApi("/api/remove", ui.dragged.from);
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

    if (event.code === "Space") {
        event.preventDefault();
        if (ui.state && ui.state.can_peel) {
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

requestApi("/api/state");
