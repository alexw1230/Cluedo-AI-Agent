#General imports
import sys
import threading
import queue
import random

#Display
from grid_window import GridWindow

#Pysat logic 
from pysat.solvers import Glucose3
from pysat.formula import CNF, IDPool

#Card Names
PEOPLE = ["Green", "Scarlet", "White", "Mustard", "Plum", "Peacock"]
WEAPONS = ["Candlestick", "Dagger", "LeadPipe", "Pistol", "Rope", "Wrench"]
LOCATIONS = ["Bedroom", "Office", "DiningRoom", "Courtyard", "Bathroom", "Garage", "LivingRoom", "GameRoom", "Kitchen"]
ALL_CARDS = PEOPLE + WEAPONS + LOCATIONS

#Helper to index a card and handle any errors
def card_index(card):
    try:
        return ALL_CARDS.index(card)
    except ValueError:
        return None

#Heuristic sorting function using montecarlo sim and EV
#Scores based on expected average information gain, weighting envelope solves higher
def score_guess(matrix, guess_cards, players):
    
    cards = list(guess_cards)
    env_col = 0
    #Weights
    base_player_weight = 1
    envelope_false_weight = 4
    envelope_true_weight = 12

    outcomes = []
    #If player has one of the cards
    for card in cards:
        r = card_index(card)
        if r is None:
            continue

        for c in range(len(players)):
            if matrix[r][c] == 0:
                outcomes.append({(r, c): 1})

    #If no one has any of the cards
    no_response = {}
    valid = True
    for card in cards:
        r = card_index(card)
        if r is None:
            continue
        for c in range(len(players)):
            if matrix[r][c] == 1:
                valid = False
                break
            no_response[(r, c)] = -1
        if not valid:
            break

    if valid:
        outcomes.append(no_response)

    #If not outcomes, no info is gained
    if not outcomes:
        return 0

    #We assume all results are equally likely
    p = 1 / len(outcomes)
    expected_score = 0

    #Calculate how much info will be gained based on changes in the matrix, weighting envelope changes higher
    for outcome in outcomes:
        d = 0
        for (r, c), new_val in outcome.items():
            if matrix[r][c] != 0 or new_val == 0:
                continue
            if c == env_col:
                if new_val == 1:
                    d += envelope_true_weight
                else:
                    d += envelope_false_weight
            else:
                d += base_player_weight
        #Considering the EV based on score and probability
        expected_score += p * d

    return expected_score

#Returns the top n guesses based on above heuristic
#Will only consider info not known to be with an enemy player
#Will only consider locations that can be moved to, as inputted by user (based on dice roll and board)
def suggest_guesses(matrix, players, valid_locations, n=5):

    env_col = players.index("Envelope")
    my_col = 2 #Us
    
    #Does not allow guesses with info already known to be with another player
    other_player_cols = [
        i for i in range(len(players))
        if i not in (env_col, my_col)
    ]


    def card_known_elsewhere(card):
        r = card_index(card)
        return any(matrix[r][c] == 1 for c in other_player_cols)

    
    allowed_people = [c for c in PEOPLE if not card_known_elsewhere(c)]
    allowed_weapons = [c for c in WEAPONS if not card_known_elsewhere(c)]
    allowed_locations = [c for c in valid_locations if not card_known_elsewhere(c)]

    #Generates all candidates possible based on contstraints
    candidates = [
        (p, w, l)
        for p in allowed_people
        for w in allowed_weapons
        for l in allowed_locations
    ]

    #Scores all the candidates
    scored = []
    for guess in candidates:
        s = score_guess(matrix, guess, players)
        if s > 0:
            scored.append((guess, s))

    #Sort by score
    scored.sort(key=lambda x: x[1], reverse=True)

    #Returns the top n scores, or just all possible guesses if n >= # of guesses
    return scored if n >= len(scored) else scored[:n]

#Uses entailment to see if any symbol MUST be true or false
#returns a flag which will be true if a logical contradiction is reached
def classify_vars(cnf, vpool, debug=False):
    results = {}
    flag = False
    vars = list(vpool.id2obj.keys())

    #For all variables, solve will both true and false assumption, and then label data
    #Raise flag if any var is inconsistent
    for v in vars:
        with Glucose3(bootstrap_with=cnf) as s:
            sat_true = s.solve(assumptions=[v])
        with Glucose3(bootstrap_with=cnf) as s:
            sat_false = s.solve(assumptions=[-v])

        label = vpool.obj(v)

        if sat_true and not sat_false:
            results[label] = "TRUE"
        elif not sat_true and sat_false:
            results[label] = "FALSE"
        elif sat_true and sat_false:
            if not debug:
                results[label] = "UNKNOWN"
        else:
            results[label] = "INCONSISTENT"
            flag = True

    return results, flag

#Adds the information to global CNF that player must have card
def add_has(cnf, vpool, player, card):
    if card in ALL_CARDS:
        cnf.append([vpool.id((player, card))])

#Adds the information to global CNF that player can not have card
def add_not_has(cnf, vpool, player, card):
    if card in ALL_CARDS:
        cnf.append([-vpool.id((player, card))])

#Since players can only have n cards, once a player has n cards, they must not have any other cards
#Uses flags so that everyone is only ever processed once as this is called every turn
def propagate_max_cards_pre_classify(cnf, vpool, players, n, flags):
    with Glucose3(bootstrap_with=cnf) as s:
        for player in players:
            #Skip processed players
            if flags.get(player, False):
                continue
            #Determine all cards that must be true for player
            true_cards = []
            for thing in ALL_CARDS:
                var = vpool.id((player, thing))
                if s.solve(assumptions=[var]) and not s.solve(assumptions=[-var]):
                    true_cards.append(thing)
            #If they have n cards, they can't have any more
            #Adds this logic to global cnf
            if len(true_cards) >= n:
                for thing in ALL_CARDS:
                    if thing not in true_cards:
                        cnf.append([-vpool.id((player, thing))])
                #Player is now processed, no need to do it again
                flags[player] = True

#Converts results -> matrix for guesses and display
def build_matrix(results, players):
    mapping = {"TRUE": 1, "FALSE": -1, "UNKNOWN": 0}
    matrix = [[0 for _ in range(len(players))] for _ in range(len(ALL_CARDS))]

    for (player, card), val in results.items():
        if player in players and card in ALL_CARDS:
            matrix[ALL_CARDS.index(card)][players.index(player)] = mapping[val]

    return matrix

#Initalizes logic for common cards
#For any cards the common pile does not start with, it can never have them (common pile is static)
def setup_common_cards(cnf, vpool, common_cards):
    for card in ALL_CARDS:
        if card in common_cards:
            add_has(cnf, vpool, "Common", card)
        else:
            add_not_has(cnf, vpool, "Common", card)

#Reads in int + error handling
def safe_int(prompt, lo, hi, allow_minus_one=False):
    while True:
        try:
            val = int(input(prompt))
            if allow_minus_one and val == -1:
                return -1
            if lo <= val <= hi:
                return val
        except ValueError:
            pass
        print(f"Please enter an integer between {lo} and {hi}.")

#Reads in card + error handling
def safe_card(prompt):
    while True:
        card = input(prompt).strip()
        if card in ALL_CARDS:
            return card
        print("Invalid card name.")

#Reads in guess info
def read_guess():
    #Read person guessing
    guesser = input("Enter the player number who guessed: ")
    while True:
        try:
            guesser_idx = int(guesser) - 1
            if guesser_idx >= 0:
                break
        except ValueError:
            pass
        guesser = input("Invalid input. Enter a valid player number: ")

    # Read person
    while True:
        person = input("Enter the person: ").strip()
        if person in PEOPLE:
            break
        print("Invalid person. Choose from:", PEOPLE)

    # Read weapon
    while True:
        weapon = input("Enter the weapon: ").strip()
        if weapon in WEAPONS:
            break
        print("Invalid weapon. Choose from:", WEAPONS)

    # Read location
    while True:
        location = input("Enter the location: ").strip()
        if location in LOCATIONS:
            break
        print("Invalid location. Choose from:", LOCATIONS)

    # Read responder
    responder = input("Enter the player number who responded (0 if no one): ").strip()
    while True:
        try:
            responder_idx = int(responder) - 1
            break
        except ValueError:
            responder = input("Invalid input. Enter a valid player number (0 if no one): ")
    #If you recieved the card and someone responded, what is that card?
    response = None
    if guesser_idx == 0 and responder_idx != -1:
        response = input("What card did they respond with?: ").strip()

    return guesser_idx, responder_idx, response, (person, weapon, location)

#Adds all info from a guess to global cnf
def handle_guess_response(cnf, vpool, guesser_idx, responder_idx, response, guess_cards, num_players):
    #If no one responded
    if responder_idx == -1:
        for p in range(num_players):
            if p != guesser_idx:
                for card in guess_cards:
                    add_not_has(cnf, vpool, f"Player{p+1}", card)
        return
    #Everyone in between the guesser and responder (exclusive) can not have any of the cards
    curr = (guesser_idx + 1) % num_players
    while curr != responder_idx:
        for card in guess_cards:
            add_not_has(cnf, vpool, f"Player{curr+1}", card)
        curr = (curr + 1) % num_players
    #If the response is known, assign card to responder
    #Otherwise, responder has person v weapon v location
    responder_name = f"Player{responder_idx+1}"
    if response is None:
        cnf.append([vpool.id((responder_name, c)) for c in guess_cards])
    else:
        add_has(cnf, vpool, responder_name, response)

#Generates a unique id for each (player, card) combo since SAT requires unique int ids
def generate_ids(players):
    vpool = IDPool()
    for card in ALL_CARDS:
        for player in players:
            vpool.id((player, card))
    return vpool

#Adds the general game rules and obvious facts to the global cnf before any real info is gained
def general_constraints(cnf, vpool, players):
    #Every card must appear once and only once (duh)
    for card in ALL_CARDS:
        vars = [vpool.id((p, card)) for p in players]
        cnf.append(vars)
        for i in range(len(vars)):
            for j in range(i + 1, len(vars)):
                cnf.append([-vars[i], -vars[j]])
    #The envelope must contain exactly one person weapon and location
    for category in (PEOPLE, WEAPONS, LOCATIONS):
        vars = [vpool.id(("Envelope", c)) for c in category]
        cnf.append(vars)
        for i in range(len(vars)):
            for j in range(i + 1, len(vars)):
                cnf.append([-vars[i], -vars[j]])

#Initialization & Main Loop
def input_loop(update_queue, n):
    #INIT SETUP
    num_players = n - 3
    #Read in common cards
    common_cards = []
    print("Enter Common cards (END to finish):")
    while True:
        card = input("> ").strip()
        if card.upper() == "END":
            break
        if card in ALL_CARDS:
            common_cards.append(card)
        else:
            print("Invalid card.")
    #Read in player's cards
    player_cards = []
    print("Enter your cards (END to finish):")
    while True:
        card = input("> ").strip()
        if card.upper() == "END":
            break
        if card in ALL_CARDS:
            player_cards.append(card)
        else:
            print("Invalid card.")

    players = ["Envelope", "Common"] + [f"Player{i}" for i in range(1, num_players + 1)]
    real_players = players[2:] #Players not the envelope and common

    #Create cnf and vpool
    cnf = CNF()
    vpool = generate_ids(players)
    #Add general constraints
    general_constraints(cnf, vpool, players)
    #Add common card logic
    setup_common_cards(cnf, vpool, common_cards)
    #Add player logic
    for card in player_cards:
        add_has(cnf, vpool, "Player1", card)
    #Flags for propagation
    flags = {p: False for p in real_players}

    #Randomly shuffle as to not give away information later on
    random.shuffle(PEOPLE)
    random.shuffle(WEAPONS)
    random.shuffle(LOCATIONS)

    #MAIN GAME LOOP
    while True:
        try:
            #Propagate max cards
            propagate_max_cards_pre_classify(cnf, vpool, real_players, len(player_cards), flags)
            #Check if any variables are changed
            results, flag = classify_vars(cnf, vpool)
            #If no error, build matrix and update the graphics queue to print info to screen
            if not flag:
                matrix = build_matrix(results, players)
                update_queue.put(matrix)

            #Reads in user command
            cmd = input("Command (Guess / Has / Not / Get / Get_Not): ").strip().lower()
            if cmd == "guess":
                #Read and handle guess
                g, r, resp, guess = read_guess()
                handle_guess_response(cnf, vpool, g, r, resp, guess, num_players)
            elif cmd == "has":
                #Not usually used, allows a user to manually enter a player has a card
                p = safe_int("Player: ", 1, num_players)
                c = safe_card("Card: ")
                add_has(cnf, vpool, f"Player{p}", c)
            elif cmd == "not":
                #Not usually used, allows a user to manually enter a player doesn not have a card
                p = safe_int("Player: ", 1, num_players)
                c = safe_card("Card: ")
                add_not_has(cnf, vpool, f"Player{p}", c)
            elif cmd == "get":
                #Generate guesses based on a list of viable locations
                user_input = input("Enter valid locations: ").strip()
                valid_locations = [loc for loc in user_input.split() if loc in LOCATIONS]
                guesses = suggest_guesses(matrix, players, valid_locations=valid_locations, n=10)
                #The highest score is always the first element
                highscore = guesses[0][1]
                final = []
                for i, (guessinfo, score) in enumerate(guesses):
                    #Gathers together any guesses that are equal in EV to the highest value
                    if score == highscore:
                        final.append(guessinfo)
                    #Prints out guess, score, delta to highest
                    print(f"Guess Option {i+1}: {guessinfo[0]}, {guessinfo[1]}, {guessinfo[2]} | Score={score} | Delta={highscore-score}")
                #If many guesses are equally good, randomly picks one to ask
                final_guess = random.choice(final)
                print("===================")
                print(f"Final Guess: {final_guess[0]}, {final_guess[1]}, {final_guess[2]}")
                print("===================")
            elif cmd == "get_not":
                #Generate guesses based on a list of non-viable locations
                user_input = input("Enter invalid locations: ").strip()
                invalid_locations = [loc for loc in user_input.split() if loc in LOCATIONS]
                valid_locations = list(set(LOCATIONS) - set(invalid_locations))
                guesses = suggest_guesses(matrix, players, valid_locations=valid_locations, n=10)
                #The highest score is always the first element
                highscore = guesses[0][1]
                final = []
                for i, (guessinfo, score) in enumerate(guesses):
                    #Gathers together any guesses that are equal in EV to the highest value
                    if score == highscore:
                        final.append(guessinfo)
                    #Prints out guess, score, delta to highest
                    print(f"Guess Option {i+1}: {guessinfo[0]}, {guessinfo[1]}, {guessinfo[2]} | Score={score} | Delta={highscore-score}")
                #If many guesses are equally good, randomly picks one to ask
                final_guess = random.choice(final)
                print("===================")
                print(f"Final Guess: {final_guess[0]}, {final_guess[1]}, {final_guess[2]}")
                print("===================")
            else:
                print("Unknown command.")
        except Exception as e:
            print(f"Error Occured: {e}")
        
#Updates graphics on a seperate thread from the main loop        
def gui_poll(grid, update_queue):
    try:
        while True:
            grid.update(update_queue.get_nowait())
    except queue.Empty:
        pass
    grid.root.after(50, gui_poll, grid, update_queue)

#Reads in num players and inits graphics
def main():
    if len(sys.argv) < 2:
        print("Usage: python main.py <num_real_players>")
        sys.exit(1)

    try:
        num_real_players = int(sys.argv[1])
        if num_real_players < 2:
            raise ValueError
    except ValueError:
        print("Invalid number of players.")
        sys.exit(1)

    N = num_real_players + 3

    row_labels = ALL_CARDS
    col_labels = ["Envelope", "Common"] + [f"Player{i}" for i in range(1, num_real_players + 1)]

    grid = GridWindow(N, row_labels, col_labels)
    update_queue = queue.Queue()

    threading.Thread(target=input_loop, args=(update_queue, N), daemon=True).start()
    grid.root.after(50, gui_poll, grid, update_queue)
    grid.run()

if __name__ == "__main__":
    main()