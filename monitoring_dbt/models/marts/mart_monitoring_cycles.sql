with cycle_summary as (

    select
        cycle_id,
        min(observed_at) as cycle_timestamp,

        sum(requests_sent) as total_requests_sent,
        sum(successful_requests) as total_successful_requests,
        sum(failed_requests) as total_failed_requests,
        sum(pending_requests) as total_pending_requests,

        case
            when sum(expected_requests) > 0
            then
                sum(
                    least(
                        successful_requests,
                        expected_requests
                    )
                )::numeric
                / sum(expected_requests)
            else null
        end as success_rate,

        bool_and(corrected_layer_success) as cycle_success,

        count(*) filter (
            where corrected_layer_success = false
        ) as unsuccessful_layers,

        case
            when sum(requests_sent) > 0
            then
                sum(average_response_ms * requests_sent)
                / sum(requests_sent)
            else null
        end as avg_response_ms,

        count(*) filter (
            where response_performance_band = 'Fast'
        ) as fast_layers,

        count(*) filter (
            where response_performance_band = 'Moderate'
        ) as moderate_layers,

        count(*) filter (
            where response_performance_band = 'Slow'
        ) as slow_layers,

        count(*) filter (
            where response_performance_band = 'Very slow'
        ) as very_slow_layers

    from {{ ref('stg_rendering_observations') }}

    group by cycle_id

)

select *
from cycle_summary
where cycle_timestamp >= timestamptz '2026-08-14 15:00:00+00'
order by cycle_timestamp asc