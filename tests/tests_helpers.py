from picks_engine.picks import Candidate


def make_candidate(**kw):
    base = dict(market_ticker="KXNFLGAME-26OCT18DALPHI-PHI", league="NFL", pick_type="moneyline",
                description_yes="Eagles to win", description_no="Cowboys to win",
                yes_ask=0.54, no_ask=0.47, model_prob=0.61, market_prob=0.59,
                depth_yes=500, depth_no=500, game_label="Cowboys at Eagles")
    return Candidate(**(base | kw))
