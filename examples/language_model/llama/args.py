# Copyright (c) 2023 PaddlePaddle Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import argparse

import paddle

from paddlenlp.trainer.argparser import strtobool
from paddlenlp.utils.log import logger


def process_batch_size(args):
    if args.global_batch_size is None and args.local_batch_size is None:
        raise ValueError("global_batch_size or local_batch_size should be set.")
    elif args.global_batch_size is not None and args.local_batch_size is not None:
        assert args.global_batch_size // args.local_batch_size == (args.dp_degree * args.sharding_degree), (
            "global_batch_size[{}] should be divided by local_batch_size[{}] "
            "when dp_degree is [{}] and sharding_degree is [{}]".format(
                args.global_batch_size, args.local_batch_size, args.dp_degree, args.sharding_degree
            )
        )
    elif args.global_batch_size is not None and args.local_batch_size is None:
        assert (
            args.global_batch_size % (args.dp_degree * args.sharding_degree) == 0
        ), "global_batch_size[{}] should be divided by dp_degree[{}] times sharding_degree[{}]".format(
            args.global_batch_size, args.dp_degree, args.sharding_degree
        )
        args.local_batch_size = args.global_batch_size // (args.dp_degree * args.sharding_degree)
    else:
        args.global_batch_size = args.local_batch_size * args.dp_degree * args.sharding_degree
    assert args.local_batch_size % args.micro_batch_size == 0


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--model_name_or_path",
        default="facebookresearch/tiny-random-llama",
        type=str,
        # required=True,
        help="",
    )

    parser.add_argument(
        "--global_batch_size",
        default=8,
        type=int,
        help="Global batch size for all training process. None for not check the size is valid. "
        "If we only use data parallelism, it should be device_num * micro_batch_size.",
    )

    parser.add_argument(
        "--local_batch_size",
        default=1,
        type=int,
        help="Batch size per device for one step training.",
    )

    parser.add_argument(
        "--micro_batch_size",
        default=1,
        type=int,
        help="Batch size per device for one step training.",
    )

    # Train I/O config
    parser.add_argument(
        "--output_dir",
        default=None,
        type=str,
        required=True,
        help="The output directory where the training logs and checkpoints will be written.",
    )

    # Default training config
    parser.add_argument("--weight_decay", default=0.0, type=float, help="Weight decay if we apply some.")
    parser.add_argument("--grad_clip", default=0.0, type=float, help="Grad clip for the parameter.")
    parser.add_argument("--max_lr", default=1e-4, type=float, help="The initial max learning rate for Adam.")
    parser.add_argument("--min_lr", default=1e-5, type=float, help="The initial min learning rate for Adam.")
    parser.add_argument(
        "--warmup_rate", default=0.01, type=float, help="Linear warmup over warmup_steps for learing rate."
    )

    # Adam optimizer config
    parser.add_argument(
        "--adam_beta1",
        default=0.9,
        type=float,
        help="The beta1 for Adam optimizer. The exponential decay rate for the 1st moment estimates.",
    )
    parser.add_argument(
        "--adam_beta2",
        default=0.999,
        type=float,
        help="The bate2 for Adam optimizer. The exponential decay rate for the 2nd moment estimates.",
    )
    parser.add_argument("--adam_epsilon", default=1e-8, type=float, help="Epsilon for Adam optimizer.")

    # Training steps config
    parser.add_argument(
        "--max_steps",
        default=1000,
        type=int,
        help="If > 0: set total number of training steps to perform. Override num_train_epochs.",
    )
    parser.add_argument("--save_steps", type=int, default=100, help="Save checkpoint every X updates steps.")
    parser.add_argument(
        "--decay_steps",
        default=800,
        type=int,
        help="The steps use to control the learing rate. If the step > decay_steps, will use the min_lr.",
    )
    parser.add_argument("--logging_freq", type=int, default=1, help="Log every X updates steps.")
    parser.add_argument("--eval_freq", type=int, default=100, help="Evaluate for every X updates steps.")
    parser.add_argument("--eval_iters", type=int, default=10, help="Evaluate the model use X steps data.")

    # Config for 4D Parallelism

    parser.add_argument(
        "--sharding_degree", type=int, default=8, help="Sharding degree. Share the parameters to many cards."
    )

    parser.add_argument("--dp_degree", type=int, default=1, help="Data Parallelism degree.")
    parser.add_argument(
        "--mp_degree", type=int, default=1, help="Model Parallelism degree. Spliting the linear layers to many cards."
    )
    parser.add_argument(
        "--pp_degree",
        type=int,
        default=1,
        help="Pipeline Parallelism degree.  Spliting the the model layers to different parts.",
    )
    parser.add_argument(
        "--use_recompute", type=strtobool, nargs="?", const=False, help="Using the recompute to save the memory."
    )

    # add sharding stage2/3
    parser.add_argument(
        "--sharding_stage",
        type=int,
        default=1,
        help="sharding stage1/2/3. Stage 1: The optimizer states are partitioned across the processes, "
        "so that each process updates only its partition. Stage 2: The reduced gradients for updating "
        "the model weights are also partitioned such that each process retains only the gradients "
        " corresponding to its portion of the optimizer states. Stage 3: The model parameters are "
        "partitioned across the processes. stage3 will automatically collect and partition them "
        "during the forward and backward passes.",
    )

    parser.add_argument(
        "--sharding_offload", type=strtobool, nargs="?", const=False, help="sharding stage2/3 cpu offload strategy."
    )

    # Pure FP16 config
    parser.add_argument(
        "--use_pure_fp16", type=strtobool, nargs="?", const=False, help="Enable pure fp16 precision training."
    )

    parser.add_argument(
        "--scale_loss",
        type=float,
        default=32768,
        help="The value of scale_loss for fp16. This is only used for AMP training.",
    )

    parser.add_argument("--hidden_dropout_prob", type=float, default=0.1, help="The hidden dropout prob.")
    parser.add_argument(
        "--attention_probs_dropout_prob", type=float, default=0.1, help="The attention probs dropout prob."
    )
    parser.add_argument("--to_static", action="store_true", help="Whether use to_static to train.")

    parser.add_argument("--save_total_limit", type=int, default=3, help="Checkpoint save limit for training.")

    # Other config
    parser.add_argument("--seed", type=int, default=1234, help="Random seed for initialization")
    parser.add_argument(
        "--check_accuracy", type=strtobool, nargs="?", const=False, help="Check accuracy for training process."
    )
    parser.add_argument(
        "--device", type=str, default="gpu", choices=["cpu", "gpu", "xpu", "npu"], help="select cpu, gpu, xpu devices."
    )
    parser.add_argument(
        "--lr_decay_style",
        type=str,
        default="cosine",
        choices=["cosine", "linear", "none"],
        help="Learning rate decay style.",
    )
    parser.add_argument(
        "-p",
        "--profiler_options",
        type=str,
        default=None,
        help='The option of profiler, which should be in format "key1=value1;key2=value2;key3=value3".',
    )

    parser.add_argument("--max_seq_length", type=int, default=512, help="Max sequence length for finetune.")
    parser.add_argument(
        "--max_source_length",
        default=1024,
        type=int,
        help="The maximum total input sequence length after tokenization.Sequences longer than this will be truncated, sequences shorter will be padded.",
    )
    parser.add_argument(
        "--min_target_length",
        default=0,
        type=int,
        help="The minimum total sequence length for target text when generating. ",
    )
    parser.add_argument(
        "--max_target_length",
        default=142,
        type=int,
        help="The maximum total sequence length for target text after tokenization. Sequences longer than this will be truncated, sequences shorter will be padded. during ``evaluate`` and ``predict``.",
    )
    parser.add_argument(
        "--ignore_pad_token_for_loss",
        action="store_true",
        help="Whether to ignore the tokens corresponding to padded labels in the loss computation or not.",
    )
    parser.add_argument(
        "--dataset_name",
        default="squad",
        type=str,
        help="The name of the dataset to use. Selected in the list: " + "squad",
    )

    args = parser.parse_args()
    args.test_iters = args.eval_iters * 10

    # process batch size
    process_batch_size(args)
    args.accumulate_steps = args.local_batch_size // args.micro_batch_size

    if args.check_accuracy:
        if args.hidden_dropout_prob != 0:
            args.hidden_dropout_prob = 0.0
            logger.warning("The hidden_dropout_prob should set to 0 for accuracy checking.")
        if args.attention_probs_dropout_prob != 0:
            args.attention_probs_dropout_prob = 0.0
            logger.warning("The attention_probs_dropout_prob should set to 0 for accuracy checking.")

    logger.info("{:20}:{}".format("paddle commit id", paddle.version.commit))
    for arg in vars(args):
        logger.info("{:20}:{}".format(arg, getattr(args, arg)))

    return args
