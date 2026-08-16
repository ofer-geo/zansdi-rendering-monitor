with source_data as (

    select *
    from {{ source('rendering_monitor', 'rendering_observations') }}

),

cleaned as (

    select
        id as observation_id,
        cycle_id,
        worker_id,
        observed_at,
        scenario,

        scale as scale_label,

        case
            when scale ~ '^1:[0-9,]+$'
            then replace(split_part(scale, ':', 2), ',', '')::bigint
            else null
        end as scale_denominator,

        layer_label,
        layer_identifier,
        service,
        request_type,

        coalesce(requests_sent, 0) as requests_sent,
        coalesce(successful, 0) as successful_requests,
        coalesce(failed, 0) as failed_requests,
        coalesce(pending, 0) as pending_requests,

        average_response_ms,

        http_status_codes,
        status,
        nullif(trim(notes), '') as notes,
        nullif(trim(screenshot_path), '') as screenshot_path,

        case
            when coalesce(requests_sent, 0) > 0
            then successful::numeric / requests_sent
            else null
        end as success_rate,

        case
            when coalesce(requests_sent, 0) > 0
            then failed::numeric / requests_sent
            else null
        end as failure_rate,

        case
            when coalesce(failed, 0) > 0 then true
            when lower(status) <> 'working' then true
            else false
        end as has_failure,

        case
            when average_response_ms < 1000 then 'Fast'
            when average_response_ms < 5000 then 'Moderate'
            when average_response_ms < 10000 then 'Slow'
            else 'Very slow'
        end as response_performance_band

    from source_data

)

select *
from cleaned