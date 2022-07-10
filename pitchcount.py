#!/usr/bin/env python3

"""
Bullpen Usage Table Generator
"""

import sys
import statsapi
from datetime import datetime, date, timedelta
import copy


# Global variables
INCLUDE_CURRENT = True  # include games currently in process
NUM_DAYS = 7  # day length of table
NO_PITCHES = "-"  # value to display if no pitches on day
LAST_SHORT = 3  # recent sum of multiple days to display (must be smaller than table game count)
LAST_LONG = 5  # recent sum of multiple days to display (must be smaller than table game count)
VERT_BREAK = "  "  # vertical break text in output table


def get_team_id(name, league_id):
    """
    lookup team id based on team name, city, abbreviation, or file code
    Returns full team dictionary if multiple found, team id only if single
    Must specify league id
    """
    teams = statsapi.lookup_team(name, activeStatus="Y", season=datetime.now().year, sportIds=league_id)
    if len(teams) > 1:
        return teams
    if len(teams) == 0:
        return "Not Found"
    return teams[0]['id']


def get_roster(team_id):
    """
    returns roster pull from api based on team id
    """
    roster = statsapi.get('team_roster', {'teamId': team_id}, force=False)['roster']
    return roster


def get_position(roster, position_id):
    """
    Based on input roster in raw format,
    returns list of player ids
    at given position code (as text)
    and dict of players with player names
    """
    players = []
    player_names = {}
    for player in roster:
        if player['position']['code'] == position_id:
            player_id = player['person']['id']
            players.append(player_id)
            player_names[player_id] = player['person']['fullName']
    return players, player_names


def get_games(team_id, league_id, start_date, end_date):
    """
    Finds recent game set based on team and day interval.
    returns dict of game ids with tuple of date and number of
    team-game on day (i.e. 2 = 2nd game of doubleheader)
    """
    schedule = statsapi.schedule(date=None,
                                 start_date=start_date,
                                 end_date=end_date,
                                 team=team_id,
                                 opponent="",
                                 sportId=league_id,
                                 game_id=None)
    games = {}
    for game in schedule:
        if (game['status'] == 'Final') or (INCLUDE_CURRENT is True):
            game_id = game['game_id']
            game_date = game['game_date']
            game_num = game['game_num']
            games[game_id] = (game_date, game_num)
    return games


def get_pitch_counts(team_id, games):
    """
    Returns dict of games with list of associated
    pitchers and pitches for specified team. For each game,
    includes tuples of pitchers and pitch counts for
    each pitcher.
    """
    # output dict
    games_pitches = {}
    for game in games:
        box = statsapi.boxscore_data(game, timecode=None)
        # determine whether team is home or away
        if box['teamInfo']['away']['id'] == team_id:
            pitchers_tag = 'awayPitchers'
        elif box['teamInfo']['home']['id'] == team_id:
            pitchers_tag = 'homePitchers'
        else:
            raise Exception("Team ID not found in game " + str(game))
        box_pitchers = box[pitchers_tag]
        # game entry in output dict
        games_pitches[game] = []
        # add pitchers to output with pitches
        for pitcher in box_pitchers:
            player_id = pitcher['personId']
            if pitcher['personId'] != 0:
                n_pitches = int(pitcher['p'])
                pitcher_game = (player_id, n_pitches)
                games_pitches[game].append(pitcher_game)
    return games_pitches


def sort_pitcher_table(pitcher_games, pitcher_starts):
    """
    Sorts input dicts of pitchers and pitch counts by
    number of starts in ascending order.
    """
    pitchers_sorted = sorted(pitcher_games.keys(), key=lambda p: pitcher_starts[p])
    pitcher_games_sorted = {}
    pitcher_starts_sorted = {}
    for pitcher in pitchers_sorted:
        pitcher_games_sorted[pitcher] = pitcher_games[pitcher]
        pitcher_starts_sorted[pitcher] = pitcher_starts[pitcher]
    return pitcher_games_sorted, pitcher_starts_sorted


def build_pitcher_table(pitchers, games_pitches):
    """
    Takes in list of pitchers and dict of games with pitchers
    and pitch counts. Returns dict of pitchers with list
    of number of pitchers in team's set of
    recent games (oldest -> newest). Pitchers sorted by
    starts in sample (ascending).
    """
    # set up outputs
    pitcher_games = {}
    pitcher_starts = {}
    for pitcher in pitchers:
        pitcher_games[pitcher] = []
        pitcher_starts[pitcher] = 0
    # iterate over games linking pitchers to pitch counts
    counter = 0
    for game in games_pitches:
        nth = 0  # nth pitcher in game counter
        for item in games_pitches[game]:
            pitcher = item[0]
            np = item[1]
            if pitcher in pitcher_games:
                # add pitches to count
                pitcher_games[pitcher].append(np)
                # count starts
                if nth == 0:
                    pitcher_starts[pitcher] += 1
            nth += 1
        # record zero pitches for all rostered pitchers not in game
        for pitcher in pitcher_games:
            if len(pitcher_games[pitcher]) == counter:
                pitcher_games[pitcher].append(NO_PITCHES)
        counter += 1
    # Sort tables and return
    return sort_pitcher_table(pitcher_games, pitcher_starts)


def pad_dates(games, pitcher_games):
    """
    Adds days without games to datasets on
    pitcher usage
    """
    # format dates
    gamedays = [datetime.strptime(games[game][0], "%Y-%m-%d") for game in games]
    # create output objects
    dates = gamedays
    pitcher_dates = copy.deepcopy(pitcher_games)
    # insert gameless days
    i = 0
    while i < (len(dates) - 1):
        diff = dates[i + 1] - dates[i]
        diff = diff.days
        if diff > 1:
            new_date = dates[i] + timedelta(days=1)
            dates.insert(i + 1, new_date)
            for pitcher in pitcher_dates:
                pitcher_dates[pitcher].insert(i + 1, NO_PITCHES)
        i += 1
    return dates, pitcher_dates


def sum_recents(pitch_counts, n_days):
    """
    Based on input list of recent pitch counts (old -> recent)
    returns sum of total pitches in specified
    number of days.
    """
    if n_days < 1:
        raise Exception("n_days must be greater than zero")
    pitches = 0
    if n_days > len(pitch_counts):
        raise Exception("Cannot sum more games than available in player data pull")
    # define date range and sum pitches
    i = len(pitch_counts) - n_days
    while i < len(pitch_counts):
        if type(pitch_counts[i]) is int:
            pitches += pitch_counts[i]
        i += 1
    return pitches


def label_dates(dates):
    """
    Takes in list of dates in date form and returns list of
    strings for outputting.
    """
    labels = []
    # format labels to output strings
    for day in dates:
        label = day.strftime("%m-%d")
        labels.append(label)
    for i in range(len(labels)):
        if (i < len(dates) - 1) and dates[i] == dates[i + 1]:  # flag second game of doubleheader
            labels[i] += "(1)"
            labels[i + 1] += "(2)"
    return labels


def format_none(n):
    """
    If n is zero, formats per global definition
    """
    if n == 0:
        return NO_PITCHES
    return n


def print_pitches(dates, pitcher_dates, pitcher_starts, pitcher_names):
    """
    Prints number of pitches for each current pitcher
    across applicable set of dates
    """
    # Create labels for dates
    date_labels = label_dates(dates)
    sum_labels = ["Last " + str(LAST_SHORT)] + ["Last " + str(LAST_LONG)]
    col_labels = ["Pitcher"] + date_labels + [VERT_BREAK] + sum_labels
    # Format column outputs
    format_str = ["{:<20}"] + ["{:<8}" for col in date_labels] + ["{:<1}"] + ["{:<6}" for col in sum_labels]
    row_breaks = ["-" * 20] + ["-" * 8 for col in date_labels] + [VERT_BREAK] + ["-" * 6 for col in sum_labels]
    format_str = " ".join(format_str)
    # Print headings
    print(format_str.format(*col_labels))
    print(format_str.format(*row_breaks))
    # Print data rows of pitchers and pitches
    starter = 0
    for pitcher in pitcher_dates:
        name = pitcher_names[pitcher][:20]
        row_data = [name]
        pitch_counts = pitcher_dates[pitcher]
        for pitches in pitch_counts:
            row_data.append(pitches)
        # add recent sums
        row_data.append(VERT_BREAK)
        row_data.append(format_none(sum_recents(pitch_counts, LAST_SHORT)))
        row_data.append(format_none(sum_recents(pitch_counts, LAST_LONG)))
        # add starter vs. reliever break line
        if starter == 0 and pitcher_starts[pitcher] > 0:
            print(format_str.format(*row_breaks))
            starter = 1
        print(format_str.format(*row_data))


def produce_table(team_text, league_id):
    """
    Executes building of output table from team name search
    and league id specification
    """
    team_id = get_team_id(team_text, league_id)
    start_date = date.today() - timedelta(days=NUM_DAYS)  # start date for table
    end_date = date.today()  # end date for table
    # Build current pitcher roster
    roster = get_roster(team_id)
    pitchers, pitcher_names = get_position(roster, '1')
    # Retrieve games for team
    games = get_games(team_id, league_id, start_date, end_date)
    # Retreive pitch counts
    games_pitches = get_pitch_counts(team_id, games)
    # Build table of pitch counts and tag starts
    pitcher_games, pitcher_starts = build_pitcher_table(pitchers, games_pitches)
    # Add non-game dates to data
    dates, pitcher_dates = pad_dates(games, pitcher_games)
    # Print output
    print_pitches(dates, pitcher_dates, pitcher_starts, pitcher_names)


def main():
    # Command line form:
    # 1. filename
    # 2. team name for search
    # 3. league code
    args = sys.argv[1:]

    if len(args) == 2:
        team_text = args[0]
        league_id = int(args[1])
        print(team_text)
        print(league_id)
        produce_table(team_text, league_id)


if __name__ == '__main__':
    main()

