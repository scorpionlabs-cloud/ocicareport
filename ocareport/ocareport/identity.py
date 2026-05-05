# coding: utf-8
"""OCI authentication and identity management."""

import os
import sys
import oci
from ocareport.utils import yellow, green, red, print_info, print_error


# Custom retry strategy for OCI API calls
custom_retry_strategy = oci.retry.RetryStrategyBuilder(
    max_attempts_check=True,
    max_attempts=5,
    total_elapsed_time_check=True,
    total_elapsed_time_seconds=20,
    retry_max_wait_between_calls_seconds=5,
    retry_base_sleep_time_seconds=2,
).get_retry_strategy()


def init_authentication(user_auth, config_file_path, config_profile):
    """
    Initialize OCI authentication.

    If user_auth is specified, uses that method only.
    Otherwise, tries all methods in order: CloudShell → Config File → Instance Principals.

    Returns: (config, signer, tenancy, auth_name, details, tenancy_id)
    """
    auth_errors = {}

    auth_methods = {
        'cs': (authenticate_cloud_shell, []),
        'cf': (authenticate_config_file, [config_file_path, config_profile]),
        'ip': (authenticate_instance_principals, [])
    }

    # If auth method specified, try only that one; otherwise try all
    methods = [auth_methods[user_auth]] if user_auth else list(auth_methods.values())

    for auth_func, args in methods:
        result = auth_func(auth_errors, *args)
        if result[0] is not None:
            return result

    # All methods failed
    for auth_type, error in auth_errors.items():
        print_error(auth_type, error)

    if user_auth:
        raise SystemExit(1)

    # Offer retry with custom config file only when input will not block automation.
    if sys.stdin.isatty():
        return retry_auth()

    raise SystemExit(1)


def retry_auth():
    """Prompt user to retry with custom config file path."""
    print(yellow("\n-- All authentication methods failed --\n"))
    retry = input(yellow("Specify another config file path? [Y/N]: ")).strip().upper()

    if retry in ("Y", "YES"):
        config_path = input(yellow("Config file path: ")).strip()
        profile = input(yellow("Profile section name: ")).strip()
        result = authenticate_config_file({}, config_path, profile)
        if result[0] is not None:
            return result
        raise SystemExit("Config file authentication failed.")
    else:
        raise SystemExit("\nAuthentication failed. Exiting.\n")


def authenticate_cloud_shell(auth_errors):
    """
    Authenticate using OCI CloudShell delegation token.

    Returns: (config, signer, tenancy, auth_name, details, tenancy_id) or (None, ...) on failure.
    """
    try:
        print(yellow("\r => Trying CloudShell authentication..."), end=' ' * 30 + '\r', flush=True)

        env_config_file = os.environ.get('OCI_CONFIG_FILE')
        env_config_section = os.environ.get('OCI_CONFIG_PROFILE')

        if not env_config_file or not env_config_section:
            auth_errors['CloudShell'] = f"Not a CloudShell session (OCI_CONFIG_FILE={env_config_file})"
            return None, None, None, None, None, None

        config = oci.config.from_file(env_config_file, env_config_section)
        oci.config.validate_config(config)
        tenancy_id = config['tenancy']

        delegation_token_file = config.get('delegation_token_file')
        with open(delegation_token_file, 'r') as f:
            delegation_token = f.read().strip()

        signer = oci.auth.signers.InstancePrincipalsDelegationTokenSigner(
            delegation_token=delegation_token
        )

        # Validate by fetching tenancy
        identity = oci.identity.IdentityClient(config=config, signer=signer)
        tenancy = identity.get_tenancy(tenancy_id).data

        return config, signer, tenancy, 'delegation_token', delegation_token_file, tenancy_id

    except Exception as e:
        auth_errors['CloudShell'] = str(e).replace("\n", " ")
        return None, None, None, None, None, None


def authenticate_config_file(auth_errors, config_file_path, config_profile):
    """
    Authenticate using OCI config file.

    Returns: (config, signer, tenancy, auth_name, details, tenancy_id) or (None, ...) on failure.
    """
    try:
        print(yellow("\r => Trying Config File authentication..."), end=' ' * 30 + '\r', flush=True)

        config = oci.config.from_file(
            file_location=config_file_path,
            profile_name=config_profile
        )
        oci.config.validate_config(config)
        tenancy_id = config['tenancy']

        signer = oci.signer.Signer(
            tenancy=tenancy_id,
            user=config['user'],
            fingerprint=config['fingerprint'],
            private_key_file_location=config.get('key_file'),
            pass_phrase=oci.config.get_config_value_or_default(config, 'pass_phrase'),
            private_key_content=config.get('key_content')
        )

        # Validate by fetching tenancy
        identity = oci.identity.IdentityClient(config=config, signer=signer)
        tenancy = identity.get_tenancy(tenancy_id).data

        return config, signer, tenancy, 'config_file', config_profile, tenancy_id

    except Exception as e:
        auth_errors['Config_File'] = str(e).replace("\n", " ")
        return None, None, None, None, None, None


def authenticate_instance_principals(auth_errors):
    """
    Authenticate using OCI Instance Principals.

    Returns: (config, signer, tenancy, auth_name, details, tenancy_id) or (None, ...) on failure.
    """
    try:
        print(yellow("\r => Trying Instance Principals authentication..."), end=' ' * 30 + '\r', flush=True)

        signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner(
            retry_strategy=custom_retry_strategy
        )
        tenancy_id = signer.tenancy_id
        config = {'region': signer.region, 'tenancy': tenancy_id}

        # Validate by fetching tenancy
        identity = oci.identity.IdentityClient(config=config, signer=signer)
        tenancy = identity.get_tenancy(tenancy_id).data

        return config, signer, tenancy, 'instance_principals', signer.region, tenancy_id

    except Exception as e:
        auth_errors['Instance_Principals'] = str(e).replace("\n", " ")
        return None, None, None, None, None, None


def get_region_subscription_list(identity_client, tenancy_id, target_region):
    """
    Get list of subscribed regions.

    - If target_region is empty: returns home region only
    - If any target is 'all': returns all subscribed regions
    - Otherwise: returns every specified region if subscribed
    """
    try:
        print(yellow("\r => Loading regions..."), end=' ' * 30 + '\r', flush=True)
        subscribed_regions = identity_client.list_region_subscriptions(tenancy_id).data

        requested_regions = target_region or []
        if isinstance(requested_regions, str):
            requested_regions = [requested_regions] if requested_regions else []

        # No target specified: return home region
        if not requested_regions:
            home = next((r for r in subscribed_regions if r.is_home_region), None)
            if home:
                print_info(green, 'Region', 'analyzed', home.region_name)
                return [home]

        # All regions requested. If all is combined with explicit regions, all wins.
        if any(region.lower() == 'all' for region in requested_regions):
            print_info(green, 'Region', 'analyzed', 'all subscribed regions')
            return subscribed_regions

        region_map = {r.region_name.lower(): r for r in subscribed_regions}
        selected_regions = []
        missing_regions = []
        for region_name in requested_regions:
            region = region_map.get(region_name.lower())
            if region:
                selected_regions.append(region)
            else:
                missing_regions.append(region_name)

        if not missing_regions:
            print_info(green, 'Regions', 'analyzed', ', '.join(r.region_name for r in selected_regions))
            return selected_regions

        all_oci_regions = {r.name.lower() for r in identity_client.list_regions().data}
        for region_name in missing_regions:
            if region_name.lower() in all_oci_regions:
                print_error(f"Region '{region_name}' is not subscribed")
            else:
                print_error(f"Region '{region_name}' does not exist")
        raise SystemExit(1)

    except oci.exceptions.ServiceError as e:
        print_error("Region error:", str(e))
        raise SystemExit(1)

def get_availability_domains(identity_client, compartment_id):
    """Get list of availability domain names for a compartment."""
    ads = oci.pagination.list_call_get_all_results(
        identity_client.list_availability_domains,
        compartment_id
    ).data
    return [ad.name for ad in ads]


def get_fault_domains(identity_client, compartment_id, availability_domain):
    """Get list of fault domain names for an availability domain."""
    fds = oci.pagination.list_call_get_all_results(
        identity_client.list_fault_domains,
        compartment_id,
        availability_domain
    ).data
    return [fd.name for fd in fds]
