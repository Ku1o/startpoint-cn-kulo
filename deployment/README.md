# Deploying StarPoint

## DISCLAIMER

**While these scripts exist to facilitate ease of deployment, they are not a one-size-fits-all solution and may not work if not properly configured.**

**THESE FILES ARE PROVIDED FOR PERSONAL USE AND NOT DESIGNED FOR CREATING PUBLICLY-AVAILABLE SERVICES. CREATING AND SERVING A PUBLICLY-AVAILABLE SERVER IS HIGHLY DISCOURAGED, ESPECIALLY WITH THESE FILES AS PROVIDED. NO AUTHOR NOR CONTRIBUTOR TO STARPOINT ENDORSES NOR ASSUMES RESPONSIBILITY OF ANY KIND FOR ANY CONSEQUENCES OF ANY KIND SHOULD ONE ATTEMPT TO MAKE AVAILABLE ANY SERVICES USING THIS REPOSITORY. BY RUNNING ANY PART OF THIS CODE, AN INDIVIDUAL AGREES TO RELEASE STARPOINT AND ITS CONTRIBUTORS OF ALL LIABILITY. VOLUNTARY ASSISTANCE WITH LOCAL SETUPS SHALL NOT BE CONSIDERED LIABILITY, NOR ENDORSEMENT.**

This folder currently contains configuration files for:

- Nginx reverse proxy configuration
- SSL self-signed certificate and key generation scripts for POSIX shells and Windows (requires OpenSSL)
- Development-container setup
- Environment setup utilities used by the supported startup scripts

The former Linux-only installer, systemd unit, and dnsmasq configuration are no longer part of this repository. The remaining POSIX helpers are kept because the project startup path still supports POSIX environments such as macOS and WSL.

Ensure you have the required dependencies for the scripts you want to run. Note that npm must be run on the target system to build dependencies. Running build tasks on another system and copying the output over may not work.

Make sure to change the host address in .env to something other than localhost!
