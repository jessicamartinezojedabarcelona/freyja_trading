import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { API_BASE_URL } from '../config/api.config';
import { buildParams } from '../config/http-params';
import { CandleQuery, CandleSeriesOut } from './market-data.models';

/** Reads the candles Freyja has already stored. The backend never calls the
 * market-data provider on a read, so a response is only ever as fresh as its
 * own `freshness` says. */
@Injectable({ providedIn: 'root' })
export class MarketDataService {
  private readonly http = inject(HttpClient);

  getCandles(query: CandleQuery): Observable<CandleSeriesOut> {
    const params = buildParams({
      instrument_id: query.instrumentId,
      data_source_code: query.dataSourceCode,
      timeframe_code: query.timeframeCode,
      start: query.start,
      end: query.end,
      limit: query.limit,
    });
    return this.http.get<CandleSeriesOut>(`${API_BASE_URL}/market-data/candles`, { params });
  }
}
