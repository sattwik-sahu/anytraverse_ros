from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, PathSubstitution
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    ns_arg = DeclareLaunchArgument(
        name="ns",
        default_value="",
        description="The namespace to start the AnyTraverse node under",
    )
    params_file_arg = DeclareLaunchArgument(
        name="params_file",
        description="The path to the YAML file containing AnyTraverse parameters",
    )
    image_topic_arg = DeclareLaunchArgument(
        name="image_topic",
        default_value="/camera/rgb/image_raw",
        description="The name of the image topic consumed by AnyTraverse",
    )
    trav_map_topic_arg = DeclareLaunchArgument(
        name="trav_map_topic",
        default_value="trav_map",
        description="The name of the topic to publish mono8 traversability maps to",
    )
    unc_map_topic_arg = DeclareLaunchArgument(
        name="unc_map_topic",
        default_value="unc_map",
        description="The name of the topic to publish mono8 uncertainty maps to",
    )
    state_topic_arg = DeclareLaunchArgument(
        name="state_topic",
        default_value="state",
        description="The name of the topic to publish AnyTraverse states to",
    )
    init_prompt_arg = DeclareLaunchArgument(
        name="init_prompt",
        description="The initial prompt for the AnyTraverse pipeline. Syntax: ``<prompt1>: <weight1>; <prompt2: weight2>[;] ...``",
    )

    # Create the AnyTraverse node (decoupled perception: Image -> mono8 maps + state)
    # NOTE: the node subscribes to relative `image_raw` so namespacing works;
    # compressed transport is negotiated subscriber-side, no republishers needed.
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
                )
            },
        ],
        remappings=[
            ("image_raw", LaunchConfiguration("image_topic")),
            ("trav_map", LaunchConfiguration("trav_map_topic")),
            ("unc_map", LaunchConfiguration("unc_map_topic")),
            ("state", LaunchConfiguration("state_topic")),
        ],
    )

    return LaunchDescription(
        [
            ns_arg,
            params_file_arg,
            image_topic_arg,
            trav_map_topic_arg,
            unc_map_topic_arg,
            state_topic_arg,
            init_prompt_arg,
            anytraverse_node,
        ]
    )
