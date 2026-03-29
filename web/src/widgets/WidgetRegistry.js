// web/src/widgets/WidgetRegistry.js
// To add a new widget type:
// 1. Create the component in this folder
// 2. Import it here and add one line to WIDGET_REGISTRY
// That's it — no other files need to change.

import MarketOverviewWidget       from './MarketOverviewWidget';
import ActionsWidget              from './ActionsWidget';
import PnLByStrategyWidget        from './PnLByStrategyWidget';
import ChartWidget                from './ChartWidget';
import MediaWidget                from './MediaWidget';
import PositionsLiveWidget        from './PositionsLiveWidget';
import PositionsScorecardWidget   from './PositionsScorecardWidget';

export const WIDGET_REGISTRY = {
  market_overview:      MarketOverviewWidget,
  actions:              ActionsWidget,
  pnl_by_strategy:      PnLByStrategyWidget,
  chart:                ChartWidget,
  media:                MediaWidget,
  positions_live:       PositionsLiveWidget,
  positions_scorecard:  PositionsScorecardWidget,
};

// Standard props contract — every widget receives exactly these props:
// {
//   config: { id, type, title, settings }  — from dashboard_layouts.widgets_json
//   isEditMode: boolean                    — false in 2.3, true in 2.4 drag mode
// }
