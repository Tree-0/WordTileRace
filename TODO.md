- [ ] Add better status indicator for whether the board is valid
    - Include detail about the reason (invalid word, invalid disjoint board)
    - Will involve either adding a different validity function, or changing the 
        current function to return additional information. Then will need to 
        change function signatures to choose which information they want


- [ ] Better handling for disjoint board -> should show visually that the board is invalid and not let you peel
- [ ] Maybe pop out letter box as draggable toolbar?
- [X] Try to fix latency
- [ ] Better indicators when other players peel
- [ ] Setting to enable auto-moving right or down when placing tiles
- [ ] Click and drag select boxes to mass delete or reorganize words
- [ ] Sometimes I get 'connected to game' and 'connection not ready yet' even when I am already playing in a match
    - Need to figure out why connectivity is so buns
- [ ] More concise GameIDs
- [ ] More explicit singleplayer option -> avoid some overhead if you actually just want to play by yourself?

- [ ] Make custom game IDs
- [ ] Ability to rematch within the same game
- [ ] Host starts game when everyone has joined
- [ ] Cap player count at 8, unless it's a custom game where everyone starts with the same rack

- [ ] Clearer dump/peel indicators
- [ ] Cooldown to prevent people from spamming dump

- [X] Make sure the win condition happens when one player has no more tiles 
    and the number of tiles in the bag is less than the number of players

- [X] Bag size multiplier
- [X] Move the help icon so that it is not in the way; put it to the right of word tile race
- [ ] Visual indicator that tiles must be connected -> i.e. disconnected tiles are yellow
