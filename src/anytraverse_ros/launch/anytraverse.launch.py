from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, PathSubstitution
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    ns_arg = DeclareLaunchArgument(
        name="ns",
        default_value="",
        description="The namespace to start the AnyTraverse nodes under",
    )
    params_file_arg = DeclareLaunchArgument(
        name="params_file",
        description="The path to the YAML file containing AnyTraverse parameters",
    )
    init_prompt_arg = DeclareLaunchArgument(
        name="init_prompt",
        description="The initial prompt for the AnyTraverse pipeline. Syntax: ``<prompt1>: <weight1>; <prompt2: weight2>[;] ...``",
    )

    # AnyTraverse perception node (Image -> mono8 maps + state).
    # All topic names come from the YAML file; only init_prompt
    # is overridable from the CLI.
    anytraverse_node = Node(
        package="anytraverse_ros",
        namespace=LaunchConfiguration("ns"),
        executable="anytraverse_node",
        name="anytraverse",
        parameters=[
            PathSubstitution(LaunchConfiguration("params_file")),
            {
                "init_prompt": ParameterValue(
                    value=LaunchConfiguration("init_prompt"), value_type=str
                ),
            },
        ],
    )

    # Velocity gating node (cmd_vel + state -> gated cmd_vel).
    # All configuration (enable flag, topic names) comes from the
    # `vel_gating` block of the same params file.
    vel_gating_node = Node(
        package="anytraverse_ros",
        namespace=LaunchConfiguration("ns"),
        executable="vel_gating_node",
        name="vel_gating",
        parameters=[
            PathSubstitution(LaunchConfiguration("params_file")),
        ],
    )

    return LaunchDescription(
        [
            ns_arg,
            params_file_arg,
            init_prompt_arg,
            anytraverse_node,
            vel_gating_node,
        ]
    )
