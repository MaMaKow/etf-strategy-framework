from ..config import SDAConfig
from ..models import State


class CashFlowManager:
    def __init__(self, cfg: SDAConfig):
        self.cfg = cfg

    def apply_monthly_savings(self, state: State, savings: float):
        ocf = state.cash_ocf
        target = self.cfg.ocf_target

        if ocf < self.cfg.ocf_low_pct * target:
            # 100 % → OCF
            state.cash_ocf += savings
            state.total_ocf_inflow += savings
        elif ocf < self.cfg.ocf_mid_pct * target:
            # 70 % ETF, 30 % OCF
            ocf_part = 0.30 * savings
            state.cash_ocf += ocf_part
            state.total_ocf_inflow += ocf_part
            # ETF part handled by order
        else:
            # 100 % ETF - handled by order
            pass