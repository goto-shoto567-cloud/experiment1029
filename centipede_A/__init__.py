from otree.api import *
import json

doc = """Centipede Game A
10ラウンド（ゲーム）を繰り返し、各ラウンドは1手のみ（継続は無し）。
利得はラウンド間で累積。ペアは固定。
"""

class C(BaseConstants):
    NAME_IN_URL = 'centipede_A'
    PLAYERS_PER_GROUP = 2
    NUM_ROUNDS = 10
    MAX_TURNS = 10
    PAYOFFS = [
        (1, 1), (0, 4), (3, 3), (2, 6), (5, 5),
        (4, 8), (7, 7), (6, 10), (9, 9), (8, 12), (11, 11)
    ]
    MAX_K = len(PAYOFFS) - 1

class Subsession(BaseSubsession):
    def creating_session(self):
        if self.round_number == 1:
            self.group_randomly()
        else:
            self.group_like_round(1)  # 固定ペア

class Group(BaseGroup):
    # 既存フィールドは残しておく（DBマイグレーション不要のため）
    k = models.IntegerField(initial=0)
    is_over = models.BooleanField(initial=False)
    action_history = models.LongStringField(initial='[]')

    def acting_role(self) -> str:
        # 奇数ラウンド=P1, 偶数ラウンド=P2
        return 'P1' if (self.subsession.round_number % 2) == 1 else 'P2'

    def safe_payoffs(self, k_val: int):
        idx = max(0, min(k_val, len(C.PAYOFFS) - 1))
        return C.PAYOFFS[idx]

    def payoff_index(self) -> int:
        # 継続回数 = ラウンド番号 - 1
        return min(max(self.subsession.round_number - 1, 0), C.MAX_K)

    def finalize_and_pay(self):
        idx = self.payoff_index()
        p1_pay, p2_pay = C.PAYOFFS[idx]
        for p in self.get_players():
            p.round_payoff = p1_pay if p.role == 'P1' else p2_pay
            p.payoff += p.round_payoff  # 累積
        self.is_over = True
        # 履歴は任意（ここではround/actionだけ軽く残す）
        return dict(event='end', k=idx, p1_pay=p1_pay, p2_pay=p2_pay,
                    history=json.loads(self.action_history))

class Player(BasePlayer):
    round_payoff = models.IntegerField(initial=0)

    # 練習問題（両者同一の入力形式に統一済）
    practice_q1_my  = models.IntegerField(label='先攻の利得', initial=0)
    practice_q1_opp = models.IntegerField(label='後攻の利得', initial=0)
    practice_q2_my  = models.IntegerField(label='先攻の利得', initial=0)
    practice_q2_opp = models.IntegerField(label='後攻の利得', initial=0)

    # ログ用途（任意）：このラウンドの選択（C/S）を記録したい場合
    action = models.StringField(
        choices=[('C', 'C（継続）'), ('S', 'S（停止）')],
        blank=True
    )

    @property
    def role(self):
        return 'P1' if self.id_in_group == 1 else 'P2'

# ===== Pages =====

class Consent(Page):
    @staticmethod
    def is_displayed(player: Player):
        return player.round_number == 1

class Instructions(Page):
    @staticmethod
    def is_displayed(player: Player):
        return player.round_number == 1

class PracticeIntro(Page):
    @staticmethod
    def is_displayed(player: Player):
        return player.round_number == 1

class PracticeQ1(Page):
    form_model = 'player'
    form_fields = ['practice_q1_my', 'practice_q1_opp']

    @staticmethod
    def is_displayed(player: Player):
        return player.round_number == 1

    @staticmethod
    def vars_for_template(player: Player):
        k = 3
        p1, p2 = C.PAYOFFS[k]
        return dict(k=k, p1=p1, p2=p2, scenario='先攻C→後攻C→先攻C→後攻S')

    @staticmethod
    def error_message(player: Player, values):
        k = 3
        p1c, p2c = C.PAYOFFS[k]
        if values['practice_q1_my'] != p1c or values['practice_q1_opp'] != p2c:
            return '解答が違う。利得表 (k=3) を確認せよ（入力は先攻→後攻の順）。'

class PracticeQ2(Page):
    form_model = 'player'
    form_fields = ['practice_q2_my', 'practice_q2_opp']

    @staticmethod
    def is_displayed(player: Player):
        return player.round_number == 1

    @staticmethod
    def vars_for_template(player: Player):
        k = 0
        p1, p2 = C.PAYOFFS[k]
        return dict(k=k, p1=p1, p2=p2, scenario='先攻Sで即終了')

    @staticmethod
    def error_message(player: Player, values):
        k = 0
        p1c, p2c = C.PAYOFFS[k]
        if values['practice_q2_my'] != p1c or values['practice_q2_opp'] != p2c:
            return '解答が違う。利得表 (k=0) を確認せよ（入力は先攻→後攻の順）。'

class MainIntro(Page):
    @staticmethod
    def is_displayed(player: Player):
        return player.round_number == 1

class ShowRole(Page):
    @staticmethod
    def is_displayed(player: Player):
        return True

    @staticmethod
    def vars_for_template(player: Player):
        return dict(
            round_no=player.round_number,
            continued_times=player.round_number - 1,
        )

class Decision(Page):
    """手番のみが表示。1クリックでそのラウンドは即終了＆清算。"""
    form_model = 'player'
    form_fields = ['action']  # ログ用途（不要なら外してOK）

    @staticmethod
    def is_displayed(player: Player):
        return player.role == player.group.acting_role()

    @staticmethod
    def vars_for_template(player: Player):
        g = player.group
        return dict(
            round_no=player.round_number,
            acting='先攻' if g.acting_role() == 'P1' else '後攻',
            continued_times=player.round_number - 1,
        )

    @staticmethod
    def before_next_page(player: Player, timeout_happened):
        g = player.group
        if not g.is_over:
            # 簡易ログ：履歴に残す（任意）
            hist = json.loads(g.action_history)
            hist.append(dict(round=player.round_number, actor=player.role, action=player.action or 'C'))
            g.action_history = json.dumps(hist)
            g.finalize_and_pay()

class WaitForOther(WaitPage):
    """非手番はここで待機。手番もDecision後にここで合流してからResultsへ。"""
    pass

class Results(Page):
    @staticmethod
    def is_displayed(player: Player):
        return player.group.is_over

    @staticmethod
    def vars_for_template(player: Player):
        g = player.group
        idx = g.payoff_index()
        p1_pay, p2_pay = C.PAYOFFS[idx]
        my_pay, opp_pay = (p1_pay, p2_pay) if player.role == 'P1' else (p2_pay, p1_pay)
        return dict(
            k=idx,
            my_pay=my_pay,
            opp_pay=opp_pay,
            round_no=player.round_number,
            continued_times=player.round_number - 1,
            num_rounds=C.NUM_ROUNDS,
            # cum_pay=player.payoff,  # 累積を見せたい時はテンプレで参照
        )

page_sequence = [
    # Consent, Instructions, PracticeIntro, PracticeQ1, PracticeQ2, MainIntro,  # ←要れば活かす
    ShowRole,
    Decision,
    WaitForOther,
    Results,
]
