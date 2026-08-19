with source_data as (

    select *
    from {{ source('rendering_monitor', 'rendering_observations') }}

),

expected_requests as (

    select
        scale_label,
        layer_identifier,
        expected_requests
    from {{ ref('expected_layer_requests') }}

),

cleaned as (

    select
        s.id as observation_id,
        s.cycle_id,
        s.worker_id,
        s.observed_at,
        s.scenario,

        s.scale as scale_label,

        case
            when s.scale ~ '^1:[0-9,]+$'
            then replace(split_part(s.scale, ':', 2), ',', '')::bigint
            else null
        end as scale_denominator,

        s.layer_label,
        s.layer_identifier,
        s.service,
        s.request_type,

        coalesce(s.requests_sent, 0) as requests_sent,
        coalesce(s.successful, 0) as successful_requests,
        coalesce(s.failed, 0) as failed_requests,
        coalesce(s.pending, 0) as pending_requests,

        e.expected_requests,

        case
            when e.expected_requests is null then false
            when coalesce(s.successful, 0) >= e.expected_requests then true
            else false
        end as corrected_layer_success,

        s.average_response_ms,

        s.http_status_codes,
        s.status,
        nullif(trim(s.notes), '') as notes,
        nullif(trim(s.screenshot_path), '') as screenshot_path,

        case
            when coalesce(s.requests_sent, 0) > 0
            then s.successful::numeric / s.requests_sent
            else null
        end as success_rate,

        case
            when coalesce(s.requests_sent, 0) > 0
            then s.failed::numeric / s.requests_sent
            else null
        end as failure_rate,

        case
            when coalesce(s.failed, 0) > 0 then true
            when lower(s.status) <> 'working' then true
            else false
        end as has_failure,

        case
            when s.average_response_ms < 1000 then 'Fast'
            when s.average_response_ms < 5000 then 'Moderate'
            when s.average_response_ms < 10000 then 'Slow'
            else 'Very slow'
        end as response_performance_band

    from source_data s

    left join expected_requests e
        on s.scale = e.scale_label
       and s.layer_identifier = e.layer_identifier

)

select *
from cleaned